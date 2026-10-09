"""Convert bounded, untrusted PDF/SVG charts to inert, metadata-free PNGs."""
import base64
import io
import math
import re
from defusedxml import ElementTree as ET

def png_result(raw):
    from PIL import Image
    Image.MAX_IMAGE_PIXELS=2_000_000
    with Image.open(io.BytesIO(raw)) as original:
        if original.width*original.height>2_000_000 or max(original.size)>4096:
            raise ValueError('数据图输出超过像素限制，请缩小图幅')
        fresh=Image.new('RGB',original.size,'white')
        if 'A' in original.getbands(): fresh.paste(original.convert('RGB'),mask=original.getchannel('A'))
        else: fresh.paste(original.convert('RGB'))
        output=io.BytesIO(); fresh.save(output,format='PNG')
    if len(output.getvalue())>4*1024*1024: raise ValueError('转换后的数据图超过 4 MB，请简化图表')
    return {'data':'data:image/png;base64,'+base64.b64encode(output.getvalue()).decode()}

def target_size(width,height):
    if not all(math.isfinite(v) and 0<v<=50000 for v in (width,height)):
        raise ValueError('数据图尺寸无效或超过限制')
    scale=min(1600/max(width,height),math.sqrt(1_900_000/(width*height)))
    return max(1,int(width*scale)),max(1,int(height*scale))

SVG_NS='http://www.w3.org/2000/svg'
TAGS=set('svg g path rect line polyline polygon circle ellipse text tspan defs clipPath linearGradient radialGradient stop use title desc metadata style pattern marker symbol'.split())

def safe_css(value):
    if re.search(r'[@\\]|expression\s*\(|(?:https?|file|data|javascript)\s*:',value,re.I):
        raise ValueError('SVG 不允许外部资源或动态样式，请改用静态 SVG/PNG')
    urls=re.findall(r'url\s*\(([^)]*)\)',value,re.I)
    for url in urls:
        if not re.fullmatch(r'#[\w.:-]+',url.strip().strip('\"\'')):
            raise ValueError('SVG 只允许文件内的图形引用')
    if len(re.findall(r'url\s*\(',value,re.I))!=len(urls): raise ValueError('SVG 资源引用格式无效')

def svg_chart(raw):
    if len(raw)>2*1024*1024: raise ValueError('SVG 数据图不超过 2 MB')
    try:
        text=raw.decode('utf-8-sig')
        # Matplotlib's fixed SVG 1.1 declaration has no internal subset; remove
        # just this known declaration without resolving its remote DTD.
        text=re.sub(r'<!DOCTYPE\s+svg\s+PUBLIC\s+[\"\']-//W3C//DTD SVG 1\.1//EN[\"\']\s+[\"\']https?://www\.w3\.org/Graphics/SVG/1\.1/DTD/svg11\.dtd[\"\']\s*>','',text)
        root=ET.fromstring(text,forbid_dtd=True,forbid_entities=True,forbid_external=True)
    except Exception: raise ValueError('SVG XML 无效，或包含禁止的 DTD/实体') from None
    def local(tag):
        if not isinstance(tag,str): raise ValueError('SVG 元素无效')
        if tag.startswith('{'):
            ns,name=tag[1:].split('}',1)
            if ns!=SVG_NS: raise ValueError('SVG 不允许外部命名空间元素')
            return name
        return tag
    if local(root.tag)!='svg': raise ValueError('文件必须为 SVG 图形')
    for parent in list(root.iter()):
        for child in list(parent):
            if child.tag in ('metadata','{'+SVG_NS+'}metadata'): parent.remove(child)
    nodes=list(root.iter())
    if len(nodes)>5000: raise ValueError('SVG 最多 5000 个元素，请简化图形')
    for node in nodes:
        name=local(node.tag)
        if name not in TAGS: raise ValueError('SVG 包含不支持的动态、嵌入或滤镜元素，请改用静态 SVG/PNG')
        if name=='style': safe_css(node.text or '')
        for attr,value in node.attrib.items():
            key=attr.split('}')[-1]
            if key.lower().startswith('on') or key in ('base','src'):
                raise ValueError('SVG 不允许事件、路径或外部资源')
            if key=='href' and not re.fullmatch(r'#[\w.:-]+',value):
                raise ValueError('SVG 只允许文件内的图形引用')
            safe_css(value)
        if len(node.text or '')>32000: raise ValueError('SVG 文字过长')
    def length(value):
        match=re.fullmatch(r'([+\-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+\-]?\d+)?)\s*(px|pt|in|cm|mm)?',value.strip())
        if not match: return None
        return float(match[1])*{'px':1,'pt':96/72,'in':96,'cm':96/2.54,'mm':96/25.4,None:1}[match[2]]
    width=length(root.get('width',''));height=length(root.get('height',''))
    box=root.get('viewBox','').replace(',',' ').split()
    if box:
        try: values=list(map(float,box))
        except ValueError: raise ValueError('SVG viewBox 无效') from None
        if len(values)!=4 or not all(math.isfinite(v) for v in values): raise ValueError('SVG viewBox 无效')
        target_size(values[2],values[3])
        width=width or values[2];height=height or values[3]
    if width is None or height is None: raise ValueError('SVG 需要有效的宽高或 viewBox')
    w,h=target_size(width,height)
    from resvg_py import svg_to_bytes
    import xml.etree.ElementTree as XML
    safe=XML.tostring(root,encoding='unicode')
    return {'figures':[png_result(svg_to_bytes(svg_string=safe,width=w,height=h,dpi=96,background='#ffffff',resources_dir=None,log_information=False))],'pages':1}

def pdf_charts(raw,capacity):
    from pypdf import PdfReader,Configuration,apply_configuration
    import pypdfium2 as pdfium
    config=Configuration(maximum_declared_stream_length=2*1024*1024,
        array_based_stream_maximum_output_length=2*1024*1024,zlib_maximum_output_length=2*1024*1024,
        lzw_maximum_output_length=2*1024*1024,run_length_maximum_output_length=2*1024*1024,
        image_maximum_buffer_size=2*1024*1024,page_tree_maximum_entries=100,page_tree_maximum_depth=20,jbig2dec_binary=None)
    with apply_configuration(config):
        reader=PdfReader(io.BytesIO(raw),root_object_recovery_limit=1000)
        if reader.is_encrypted: raise ValueError('不接受加密 PDF 数据图，请在本地解密后导入')
        count=len(reader.pages)
        if not 1<=count<=capacity: raise ValueError(f'PDF 每页作为一张图，当前最多还能添加 {capacity} 页')
        total=0;seen=set();objects=0
        def resources(value,depth=0):
            nonlocal total,objects
            if depth>8: raise ValueError('PDF 数据图嵌套过深')
            value=value.get_object() if hasattr(value,'get_object') else value
            value=value or {}
            xobjects=value.get('/XObject',{})
            if hasattr(xobjects,'get_object'): xobjects=xobjects.get_object()
            for reference in xobjects.values():
                item=reference.get_object();identity=id(item)
                if identity in seen: continue
                seen.add(identity);objects+=1
                if objects>256: raise ValueError('PDF 数据图对象过多')
                if item.get('/Subtype')=='/Image':
                    iw=int(item.get('/Width',0));ih=int(item.get('/Height',0))
                    if iw<=0 or ih<=0 or max(iw,ih)>12000 or iw*ih>20_000_000:
                        raise ValueError('PDF 内嵌图片尺寸超过限制，请缩小图片后重新导出')
                elif item.get('/Subtype')=='/Form':
                    total+=len(item.get_data())
                    if total>8*1024*1024: raise ValueError('PDF 数据图解压内容过大')
                    resources(item.get('/Resources',{}),depth+1)
        for page in reader.pages:
            content=page.get_contents()
            if content: total+=len(content.get_data())
            if total>8*1024*1024: raise ValueError('PDF 数据图解压内容过大')
            resources(page.get('/Resources',{}))
    result=[]
    with pdfium.PdfDocument(raw) as document:
        if len(document)!=count: raise ValueError('PDF 页数无法一致解析')
        for index in range(count):
            page=document[index]
            try:
                width,height=page.get_size(); w,h=target_size(width,height)
                bitmap=page.render(scale=min(w/width,h/height),may_draw_forms=False,draw_annots=False)
                try:
                    with bitmap.to_pil() as image:
                        output=io.BytesIO();image.save(output,format='PNG')
                    result.append(png_result(output.getvalue()))
                finally: bitmap.close()
            finally: page.close()
    return {'figures':result,'pages':count}

def import_chart(raw,options):
    kind=options.get('kind');capacity=options.get('capacity',5)
    if type(capacity) is not int or not 1<=capacity<=5: raise ValueError('最多 5 张数据图，请先移除已有图表')
    if kind=='svg': return svg_chart(raw)
    if kind=='pdf': return pdf_charts(raw,capacity)
    raise ValueError('数据图格式无效')
