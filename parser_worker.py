"""Short-lived parser: stdin bytes, bounded JSON stdout, no upload files or network."""
import base64
import io
import json
import sys
import warnings

MAX_STREAM = 2 * 1024 * 1024

def pdf_text(raw):
    from pypdf import PdfReader, Configuration, apply_configuration
    config = Configuration(maximum_declared_stream_length=MAX_STREAM,
        array_based_stream_maximum_output_length=MAX_STREAM, zlib_maximum_output_length=MAX_STREAM,
        lzw_maximum_output_length=MAX_STREAM, run_length_maximum_output_length=MAX_STREAM,
        image_maximum_buffer_size=MAX_STREAM, page_tree_maximum_entries=100,
        page_tree_maximum_depth=20, xform_maximum_invocations_per_extraction=100,
        jbig2dec_binary=None)
    with apply_configuration(config):
        reader = PdfReader(io.BytesIO(raw), root_object_recovery_limit=1000)
        if reader.is_encrypted: raise ValueError('不接受加密 PDF，请在本地解密后导入')
        count = len(reader.pages)
        if not 1 <= count <= 20: raise ValueError('过程 PDF 限 1–20 页')
        chunks = []; total = 0; work = 0
        for page in reader.pages:
            content = page.get_contents()
            if content:
                work += len(content.get_data())
                if work > 4 * MAX_STREAM: raise ValueError('PDF 解压后内容过大，请改为粘贴文字')
            value = page.extract_text() or ''
            total += len(value)
            if total > 18000: raise ValueError('过程文字超过 18000 字符，请精简后导入')
            chunks.append(value)
        text = '\n'.join(chunks)
        if len(text.strip()) < 20: raise ValueError('PDF 文字不足或为扫描件，请手动填写')
        return {'text':text,'pages':count}

def image_data(raw):
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = 2_000_000
    warnings.simplefilter('error', Image.DecompressionBombWarning)
    with Image.open(io.BytesIO(raw)) as image:
        if image.format not in ('PNG','JPEG') or image.width*image.height > 2_000_000 or max(image.size)>4096:
            raise ValueError('图片限 PNG/JPEG、200 万像素且边长不超过 4096')
        image.verify()
    with Image.open(io.BytesIO(raw)) as image:
        # Copy pixels into a new image: discard EXIF, comments and other source metadata.
        fresh = Image.new('RGB',image.size, 'white')
        if 'A' in image.getbands(): fresh.paste(image.convert('RGB'),mask=image.getchannel('A'))
        else: fresh.paste(image.convert('RGB'))
        target = io.BytesIO(); fresh.save(target,format='PNG')
        safe = target.getvalue()
        if len(safe)>4*1024*1024: raise ValueError('规范化图片超过 4 MB，请缩小图片')
        return {'data':'data:image/png;base64,'+base64.b64encode(safe).decode()}

if __name__ == '__main__':
    try:
        raw=sys.stdin.buffer.read(8*1024*1024+1)
        if len(raw)>8*1024*1024: raise ValueError('文件过大')
        answer = pdf_text(raw) if sys.argv[1]=='pdf' else image_data(raw)
        sys.stdout.write(json.dumps(answer,ensure_ascii=True))
    except ValueError as exc:
        sys.stdout.write(json.dumps({'error':str(exc)[:160]},ensure_ascii=True)); sys.exit(1)
    except Exception:
        sys.stdout.write(json.dumps({'error':'文件无效或超出解析限制，请改用文字或较小图片'},ensure_ascii=True)); sys.exit(1)
