"""Validate a separately issued video image manifest before physical probe traffic."""
from pathlib import Path
import hashlib,json,re
from startup_status_identity import validate_startup_contract

C_SOURCE='303b51d21b3004ddf5780c502ae5c1f3b81cefb6'
B_SOURCE='6cc8ea4173d2a720f741e80b7cbd9279558ee93a'
# Known checkpoint images cannot execute the new video protocol. Metadata or a
# renamed file must not turn these exact historical bytes into a video image.
HISTORICAL_BITS={
    'a907a50af0528d2149b369a404eb0eade3b282a14e1e9b1e7419acf66b43c0cd',
    '5080a27bf5f2f0ad362179a40e61e5903fd847db5801e029cbc5ea704ec6aae1',
    '29a28d27516dfc408ac84a5f2a8a19e2ae1de975ce6bee67b1668de4c213c91e',
}
def verify_image_manifest(path):
    path=Path(path).resolve();m=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(m,dict):raise ValueError('image manifest must be an object')
    if m.get('scope')!='ACX750_200T_ETHERNET_VIDEO_IMAGE':raise ValueError('new video image manifest required')
    if m.get('C_source')!=C_SOURCE or m.get('B_source')!=B_SOURCE:raise ValueError('frozen C/B identity mismatch')
    if (m.get('part')!='xc7a200tfbg484-2' or type(m.get('core_MHz')) is not int or m['core_MHz']!=150
        or type(m.get('pause')) is not int or m['pause']!=0):raise ValueError('frozen device/clock/pause mismatch')
    if m.get('input_dimensions')!=[960,540] or m.get('output_dimensions')!=[1920,1080]:raise ValueError('video geometry mismatch')
    if m.get('physical_IO_signoff') is not True:raise ValueError('physical I/O implementation not signed off')
    if not all(type(m.get(k)) is int and m[k] in (0,1) for k in ['actual_PHY_RX_delay','actual_PHY_TX_delay']):raise ValueError('actual PHY delay selection missing')
    validate_startup_contract(m)
    verified=[]
    for key in ['BIT','LTX']:
        item=m.get(key)
        if key=='LTX' and item is None:continue
        if not isinstance(item,dict):raise ValueError('BIT file identity required')
        if not isinstance(item.get('file'),str) or not item['file']:raise ValueError(key+' file path required')
        relative=Path(item['file'])
        if relative.is_absolute() or relative.drive or '..' in relative.parts:raise ValueError('image path must be package relative')
        if not isinstance(item.get('sha256'),str) or not re.fullmatch('[0-9a-f]{64}',item['sha256']):raise ValueError(key+' SHA256 format invalid')
        f=(path.parent/relative).resolve()
        if not f.is_relative_to(path.parent) or not f.is_file():raise ValueError('image path missing or outside package')
        if f.stat().st_size==0:raise ValueError(key+' file is empty')
        digest=hashlib.sha256(f.read_bytes()).hexdigest()
        if digest!=item['sha256']:raise ValueError(key+' hash mismatch')
        if key=='BIT' and digest in HISTORICAL_BITS:raise ValueError('historical non-video checkpoint BIT rejected')
        verified.append({'kind':key,'file':str(f),'bytes':f.stat().st_size,'sha256':digest})
    return {'manifest_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'manifest':m,'files':verified,
            'scope':'LOCAL_FILES_AND_DECLARED_IMAGE_METADATA_ONLY_NOT_HARDWARE_READBACK'}
