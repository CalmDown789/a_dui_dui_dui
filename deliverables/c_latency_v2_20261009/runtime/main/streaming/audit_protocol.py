"""Independent raw header reader. Does not import the client or its decoder."""
from types import SimpleNamespace
import struct,zlib
HEADER=struct.Struct('!4sBBH16sIIIIIHHIIII')
def parse(raw):
    if len(raw)<64:raise ValueError('short header')
    magic,version,kind,flags,session,frame,seq,offset,size,fcrc,n,status,progress,reserved,pcrc,hcrc=HEADER.unpack_from(raw)
    if (magic,version) not in ((b'EVF1',1),(b'EVF2',2)) or len(raw)!=64+n or n>1024:
        raise ValueError('raw format/length')
    if zlib.crc32(raw[:60])!=hcrc or zlib.crc32(raw[64:])!=pcrc:raise ValueError('raw CRC')
    return version,SimpleNamespace(type=kind,flags=flags,session=session,frame_id=frame,sequence=seq,
        offset=offset,frame_bytes=size,frame_crc=fcrc,status=status,next_offset=progress,reserved=reserved,
        payload=raw[64:],payload_crc=pcrc)
