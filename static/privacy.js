'use strict';
// Shared import/export guards. These also run under Node for regression tests.
const LabPrivacy = (() => {
  const object = x => x && typeof x === 'object' && !Array.isArray(x);
  function chartKind(file) {
    const extension=String(file.name??'').toLowerCase().split('.').pop();
    const kind={pdf:'pdf',svg:'svg',png:'png',jpg:'jpeg',jpeg:'jpeg'}[extension];
    if(!kind)throw Error('实验数据图支持 PDF、PNG、SVG 和 JPEG');
    const expected={pdf:'application/pdf',svg:'image/svg+xml',png:'image/png',jpeg:'image/jpeg'}[kind];
    if(file.type&&file.type!==expected&&file.type!=='application/octet-stream')throw Error('文件扩展名与类型不一致');
    return kind;
  }
  function text(x, limit) {
    if (typeof x !== 'string' || x.length > limit) throw Error('项目文字格式或长度无效');
    return x;
  }
  function imageURL(value) {
    text(value, 6 * 1024 * 1024);
    const match = /^data:image\/(png|jpeg);base64,([A-Za-z0-9+/]+={0,2})$/.exec(value);
    if (!match || match[2].length % 4) throw Error('图片必须为完整的 PNG/JPEG 数据');
    const raw = atob(match[2]);
    if (raw.length > 4 * 1024 * 1024) throw Error('单张图不超过 4 MB');
    if (match[1] === 'png' ? !raw.startsWith('\x89PNG\r\n\x1a\n') : !raw.startsWith('\xff\xd8\xff')) throw Error('图片类型与内容不一致');
    return value;
  }
  function cleanProject(project, experiments) {
    if (!object(project) || project.version !== 1 || !Number.isInteger(project.experiment) || project.experiment < 1 || project.experiment > 10 || !object(project.state)) throw Error('无效项目');
    const source = project.state, columns = experiments[project.experiment - 1].columns;
    if (!object(source.metadata) || !Array.isArray(source.rows) || source.rows.length > 10000 || !object(source.params) || !Array.isArray(source.figures) || source.figures.length > 5) throw Error('项目内容无效');
    const metadata = Object.fromEntries(['date', 'name', 'studentId', 'group'].map(k => [k, text(source.metadata[k] ?? '', 100)]));
    const rows = source.rows.map(row => {
      if (!object(row)) throw Error('数据行无效');
      return Object.fromEntries(columns.map(c => {
        const v = row[c];
        if (typeof v === 'number' && Number.isFinite(v)) return [c, v];
        return [c, text(v, 256)];
      }));
    });
    const allowed = {2:['wavelength_nm','fwhm_deg','instrument_deg','K'],3:['fit_min','fit_max'],4:['fit_min','fit_max','rate'],7:['fit_min','fit_max','length_mm'],10:['geometry']}[project.experiment] ?? [];
    const params = Object.fromEntries(allowed.filter(k => Object.hasOwn(source.params, k)).map(k => [k, text(String(source.params[k]), 80)]));
    const figures = source.figures.map(f => {
      if (!object(f)) throw Error('图表无效');
      return {data: imageURL(f.data), caption: text(f.caption ?? '', 200)};
    });
    // Never spread imported state: unknown properties, including credentials, are discarded.
    return {version:1, experiment:project.experiment, state:{metadata, rows, params, figures, chartNotes:text(source.chartNotes ?? '',18000), process:text(source.process,18000), report:text(source.report,18000), dataKind:source.dataKind === 'simulation' ? 'simulation' : 'real'}};
  }
  function csvCell(value) {
    let s = String(value ?? '');
    const numeric = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(s.trim()) && Number.isFinite(Number(s));
    if (!numeric && /^[\s\x00-\x1f\x7f]*[=+\-@]/.test(s)) s = "'" + s;
    return /[",\r\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  }
  const bytes64 = bytes => {
    let value = '';
    for (let i=0;i<bytes.length;i+=8192) value += String.fromCharCode(...bytes.subarray(i,i+8192));
    return btoa(value);
  };
  function from64(s, max) {
    if (typeof s !== 'string' || s.length > max*4/3+8 || !/^[A-Za-z0-9+/]+={0,2}$/.test(s) || s.length%4) throw Error('加密备份格式无效');
    return Uint8Array.from(atob(s), c => c.charCodeAt(0));
  }
  async function key(password, salt, usage) {
    if (typeof password !== 'string' || password.length < 12 || password.length > 128) throw Error('备份密码需 12–128 个字符，请妥善保管');
    const material = await crypto.subtle.importKey('raw', new TextEncoder().encode(password), 'PBKDF2', false, ['deriveKey']);
    return crypto.subtle.deriveKey({name:'PBKDF2',salt,iterations:310000,hash:'SHA-256'}, material, {name:'AES-GCM',length:256}, false, usage);
  }
  async function encrypt(project, password) {
    const salt=crypto.getRandomValues(new Uint8Array(16)),iv=crypto.getRandomValues(new Uint8Array(12));
    const plain=new TextEncoder().encode(JSON.stringify(project));
    if (plain.length > 16*1024*1024) throw Error('项目过大，请减少图表后备份');
    const encrypted=await crypto.subtle.encrypt({name:'AES-GCM',iv,additionalData:new TextEncoder().encode('materials-lab-v2')}, await key(password,salt,['encrypt']), plain);
    return {format:'materials-lab-encrypted',version:2,kdf:'PBKDF2-SHA256-310000',salt:bytes64(salt),iv:bytes64(iv),ciphertext:bytes64(new Uint8Array(encrypted))};
  }
  async function decrypt(envelope, password) {
    if (!object(envelope) || envelope.format !== 'materials-lab-encrypted' || envelope.version!==2 || envelope.kdf !== 'PBKDF2-SHA256-310000') throw Error('不支持的加密备份格式');
    const salt=from64(envelope.salt,16),iv=from64(envelope.iv,12),encrypted=from64(envelope.ciphertext,16*1024*1024+16);
    if (salt.length!==16 || iv.length!==12) throw Error('加密参数无效');
    try {
      const plain=await crypto.subtle.decrypt({name:'AES-GCM',iv,additionalData:new TextEncoder().encode('materials-lab-v2')}, await key(password,salt,['decrypt']), encrypted);
      return JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(plain));
    } catch { throw Error('密码错误或备份损坏，未恢复任何资料'); }
  }
  return {imageURL,chartKind,cleanProject,csvCell,encrypt,decrypt};
})();
if (typeof module !== 'undefined') module.exports = LabPrivacy;
