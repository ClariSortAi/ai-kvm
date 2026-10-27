"""Read the linked ESP32 ELF; verify the BIOS report maps actually in the image."""
import json
import struct
from pathlib import Path

root = Path(__file__).resolve().parents[1]
elf = (root/"artifacts/firmware/aikvm.ino.elf").read_bytes()
assert elf[:6] == b"\x7fELF\x01\x01", "Expected little-endian ELF32"
offset = struct.unpack_from("<I",elf,32)[0]
entry_size, count = struct.unpack_from("<HH",elf,46)
sections = [struct.unpack_from("<10I",elf,offset+i*entry_size) for i in range(count)]
symbols = {}
for section in sections:
    if section[1] != 2:
        continue
    strings = sections[section[6]]
    names = elf[strings[4]:strings[4]+strings[5]]
    for position in range(section[4],section[4]+section[5],section[9]):
        name, value, size, info, other, index = struct.unpack_from("<IIIBBH",elf,position)
        label = names[name:names.find(b"\0",name)].decode(errors="replace")
        if any(token in label for token in ("bootKeyboardDescriptor","bootMouseDescriptor","desktopDescriptor")):
            owner = sections[index]
            start = owner[4]+value-owner[3]
            symbols[label] = elf[start:start+size]


def hid_inputs(data):
    cursor=0
    size=count=report_id=0
    bits={}
    ids=[]
    while cursor<len(data):
        header=data[cursor]; cursor+=1
        assert header!=0xFE
        length=(0,1,2,4)[header&3]
        payload=data[cursor:cursor+length]; cursor+=length
        value=int.from_bytes(payload,"little")
        item_type=(header>>2)&3
        tag=header>>4
        if item_type==1:
            if tag==7: size=value
            elif tag==8: report_id=value; ids.append(value)
            elif tag==9: count=value
        if item_type==0 and tag==8:
            bits[report_id]=bits.get(report_id,0)+size*count
    return {key:value//8 for key,value in bits.items()},ids


assert len(symbols)==3, f"Expected three linked descriptor maps, found {list(symbols)}"
result={}
for name,data in symbols.items():
    inputs, ids=hid_inputs(data)
    result[name]={"descriptor_bytes":len(data),"input_bytes_by_report":inputs,"report_ids":ids}
    if "bootKeyboard" in name:
        assert inputs=={0:8} and not ids, "BIOS keyboard must be exactly 8 bytes without a report ID"
    elif "bootMouse" in name:
        assert inputs=={0:5} and not ids
    else:
        assert inputs=={1:8,2:5,7:4}
(root/"artifacts/usb-descriptor-check.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
print(json.dumps(result,indent=2))
