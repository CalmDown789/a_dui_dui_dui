"""Verify prepared Y input and frozen Golden files before video traffic."""
from pathlib import Path
import hashlib,json
from video_protocol import INPUT_BYTES,OUTPUT_BYTES
from video_image_identity import C_SOURCE,B_SOURCE


def verify_sequence(path):
    path=Path(path).resolve();m=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(m,dict):raise ValueError('sequence manifest must be an object')
    if m.get('input_dimensions')!=[960,540] or m.get('output_dimensions')!=[1920,1080]:raise ValueError('frozen geometry required')
    if m.get('C_source')!=C_SOURCE or m.get('B_source')!=B_SOURCE:raise ValueError('frozen C/B identity required')
    if m.get('dtype')!='UINT8_Y_RASTER_ROW_MAJOR':raise ValueError('uint8 Y raster format required')
    frames=m.get('frames')
    if not isinstance(frames,list) or len(frames)<2:raise ValueError('at least two continuous frames required')
    prepared=[];identities=[]
    for i,f in enumerate(frames):
        if not isinstance(f,dict) or type(f.get('frame_id')) is not int or f['frame_id']!=i:
            raise ValueError('continuous frame_ids0..N-1 required')
        pair=[];entry={'frame_id':i}
        for role,size in [('input',INPUT_BYTES),('golden',OUTPUT_BYTES)]:
            name=f.get(role+'_file')
            if not isinstance(name,str) or not name:raise ValueError('missing '+role+' path')
            relative=Path(name)
            if relative.is_absolute() or relative.drive or '..' in relative.parts:raise ValueError('sequence paths must be package relative')
            file=(path.parent/relative).resolve()
            if not file.is_relative_to(path.parent):raise ValueError('sequence path escapes package')
            data=file.read_bytes();digest=hashlib.sha256(data).hexdigest()
            if len(data)!=size or digest!=f.get(role+'_sha256'):raise ValueError(role+' size/SHA256 mismatch')
            pair.append(data);entry[role]={'file':str(file),'bytes':size,'sha256':digest}
        prepared.append(tuple(pair));identities.append(entry)
    if len({f['input']['sha256'] for f in identities})!=len(frames):raise ValueError('each input frame must be distinct')
    return prepared,{'manifest_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'frames':identities,
                     'scope':'PREPARED_INPUT_AND_GOLDEN_FILES_ONLY_NOT_BOARD_OUTPUT'}
