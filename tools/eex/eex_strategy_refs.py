"""Bounded EEX decoding without executing commands or evaluating variables."""
import json,re,struct
from pathlib import Path
SCHEMA=json.loads(Path(__file__).with_name('eex-opcodes65.json').read_text(encoding='utf-8'))
class DecodeError(ValueError):
 def __init__(self,offset,message):self.offset=offset;super().__init__(message)

class Decoder:
 def __init__(self,b):self.b=b;self.p=0;self.end=len(b);self.wide=False;self.instructions=[]
 def word(self):
  if self.p+2>self.end:raise DecodeError(self.p,'truncated WORD')
  n=struct.unpack_from('<H',self.b,self.p)[0];self.p+=2;return n
 def arg(self,tag):
  start=self.p
  if tag!=1 and self.word()!=tag:raise DecodeError(start,f'expected argument tag {tag:02X}')
  off=self.p
  if tag==5:
   z=self.b.find(b'\0',self.p,self.end)
   if z<0:raise DecodeError(off,'unterminated string')
   value=self.b[self.p:z].decode('gbk','replace');self.p=z+1
  elif tag==4:
   if self.p+4>self.end:raise DecodeError(off,'truncated DWORD')
   value=struct.unpack_from('<I',self.b,self.p)[0];self.p+=4
  else:value=self.word()
  return dict(tag=tag,offset=off,value=value)
 def instruction(self,block,record,depth,condition=False):
  if depth>128:raise DecodeError(self.p,'excessive nesting')
  start=self.p
  if self.wide:raise DecodeError(start,'wide debug instructions not supported')
  op=self.word();key=f'{op:02X}'
  if key not in SCHEMA:raise DecodeError(start,f'unsupported opcode {op:04X}')
  args=[]
  if op==5:
   for _ in range(2):
    a=self.arg(0x35);args.append(a)
    for i in range(a['value']):args.append(self.arg(1))
  else:
   tags=SCHEMA[key]['args']
   if op in (6,0x4a):tags=tags+[0x38]*5+[0x39]*5
   if op in (0x46,0x47):tags=tags*(20 if op==0x46 else 80)
   for tag in tags:args.append(self.arg(tag))
  ins=dict(offset=start,end=self.p,opcode=op,name=SCHEMA[key]['name'],args=args,block=block,record=record,depth=depth,condition=condition)
  self.instructions.append(ins)
  if op==1:
   self.instruction(block,record,depth+1,True)
   self.body(block,record,depth+1)
  return op
 def body(self,block,record,depth):
  size=self.word();end=self.p+size;old=self.end
  if end>old:raise DecodeError(self.p-2,'body exceeds enclosing record')
  self.end=end
  while self.p<end:self.instruction(block,record,depth)
  self.end=old
 def decode(self):
  if len(self.b)<10 or self.b[:4]!=b'EEX\0':raise DecodeError(0,'not an EEX resource')
  version,kind=self.b[4:6]
  if version>=2 or (version==1 and kind>2):raise DecodeError(4,'unknown EEX version')
  if kind==0:table=16
  else:
   self.p=6
   while True:
    tag=self.word();size=self.word()
    if self.p+size>self.end:raise DecodeError(self.p,'truncated metadata')
    self.p+=size
    if tag==1:self.wide=True
    if tag==0:break
   table=self.p
  self.p=table;first=self.word()|self.word()<<16
  if first<table+4 or (first-table)%4 or first>len(self.b):raise DecodeError(table,'invalid offset table')
  offsets=list(struct.unpack_from('<'+'I'*((first-table)//4),self.b,table))
  if offsets!=sorted(set(offsets)) or offsets[-1]>=len(self.b):raise DecodeError(table,'invalid block offsets')
  for block,start in enumerate(offsets):
   self.p=start;self.end=offsets[block+1] if block+1<len(offsets) else len(self.b)
   count=self.word()
   for record in range(count):
    if self.wide:self.word()
    size=self.word();end=self.p+size;old=self.end
    if end>old:raise DecodeError(self.p-2,'record exceeds block')
    self.end=end
    while self.instruction(block,record,0,True)!=0:pass
    if self.p<end:self.body(block,record,0)
    if self.p!=end:raise DecodeError(self.p,'record has undecoded trailing bytes')
    self.end=old
   if self.p!=self.end:raise DecodeError(self.p,'block has undecoded trailing bytes')
  return self.instructions

def decode(b):
 d=Decoder(b)
 try:
  return dict(complete=True,instructions=d.decode(),errors=[])
 except (DecodeError,UnicodeDecodeError) as e:
  # Do not call partial prefix matches confirmed references.
  return dict(complete=False,instructions=[],errors=[dict(offset=getattr(e,'offset',d.p),reason=str(e))])

def strategy_references(b):
 """Locate literal IDs in validated records; dynamic expressions stay unresolved.

 Offsets address the original file. This is a syntax audit, not proof that any
 condition executes, nor a data-flow analysis of integer/pointer variables.
 """
 parsed=decode(b)
 result=dict(complete=parsed['complete'],instruction_count=len(parsed['instructions']),
             references=[],risks=[],errors=parsed['errors'])
 for ins in parsed['instructions']:
  op=ins['opcode'];a=ins['args']
  location={k:ins[k] for k in ('block','record','depth','condition')}
  def risk(reason):
   result['risks'].append(dict(offset=ins['offset'],reason=reason,**location))
  if op==0x72 and a[0]['value']==4:
   # Runtime skips exactly one separator: shipped scripts use LF, not comma.
   # Accept canonical numeric prefixes only; do not trim or collapse whitespace.
   text=a[1]['value'];tokens=[];pos=0
   for _ in range(3):
    match=re.match(r'-?\*?[0-9]+(?=[^0-9*\-]|$)',text[pos:])
    if not match:break
    tokens.append(match[0]);pos+=len(match[0])
    if pos<len(text):pos+=1
   if len(tokens)<3:
    risk('72/4 noncanonical numeric expression requires interpreter review');continue
   if '*' in tokens[0]:
    risk('72/4 strategy ID comes from an integer variable');continue
   sid=int(tokens[0])
   if not 0<=sid<144:
    risk('72/4 strategy literal outside canonical 0..143; BYTE conversion requires review');continue
   result['references'].append(dict(offset=a[1]['offset'],strategy=sid,kind='EEX_72_4',
     width=len(tokens[0]),encoding='decimal_ascii',text=a[1]['value'],**location))
  elif op==0x78 and 0x200<=a[3]['value']<0x290:
   result['references'].append(dict(offset=a[3]['offset'],strategy=a[3]['value']-0x200,
     kind='EEX_78_strategy_field',width=2,encoding='u16le_plus_0x200',mode=a[1]['value'],
     subject_raw=a[2]['value'],subject_dynamic=0xefff<=a[2]['value']<0xffff,**location))
  elif op==0x77 and a[0]['value'] in (0,1):
   risk('77 pointer arithmetic/write requires strategy-address data-flow review')
  elif op==0x72 and a[0]['value']==5:
   risk('72/5 personal-effect parameters require separate effect-namespace review')
 return result
