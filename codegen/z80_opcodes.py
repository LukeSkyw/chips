#-------------------------------------------------------------------------------
#   z80_opcodes.py
#   Generate huge switch/case Z80 instruction decoder.
#   See: 
#       http://www.z80.info/decoding.htm
#       http://www.righto.com/2014/10/how-z80s-registers-are-implemented-down.html
#       http://www.z80.info/zip/z80-documented.pdf
#       https://www.omnimaga.org/asm-language/bit-n-(hl)-flags/5/?wap2
#
#   FIXME: long sequences of prefixes 0xDD/0xFD are currently handled wrong!
#-------------------------------------------------------------------------------
import sys

# tab-width for generated code
TabWidth = 2

# the output path
OutPath = '../chips/_z80_opcodes.h'

# the target file handle
Out = None

# 8-bit register table, the 'HL' entry is for instructions that use
# (HL), (IX+d) and (IY+d), and will be patched to 'IX' or 'IY' for
# the DD/FD prefix instructions
r = [ 'B', 'C', 'D', 'E', 'H', 'L', 'HL', 'A' ]

# the same, but the 'HL' item is never patched to IX/IY, this is
# for indexed instructions that load into H or L (e.g. LD H,(IX+d))
r2 = [ 'B', 'C', 'D', 'E', 'H', 'L', 'HL', 'A' ]

# 16-bit register table, with SP
rp = [ 'BC', 'DE', 'HL', 'SP' ]

# 16-bit register table, with AF (only used for PUSH/POP)
rp2 = [ 'BC', 'DE', 'HL', 'AF' ]

# condition-code table (for conditional jumps etc)
cond = [
    '!(c->F&Z80_ZF)',  # NZ
    '(c->F&Z80_ZF)',   # Z
    '!(c->F&Z80_CF)',   # NC
    '(c->F&Z80_CF)',    # C
    '!(c->F&Z80_PF)',   # PO
    '(c->F&Z80_PF)',    # PE
    '!(c->F&Z80_SF)',   # P
    '(c->F&Z80_SF)'     # M
]

# the same as 'human readable' flags for comments
cond_cmt = [ 'NZ', 'Z', 'NC', 'C', 'PO', 'PE', 'P', 'M' ]

# 8-bit ALU instructions command names
alu_cmt = [ 'ADD', 'ADC', 'SUB', 'SBC', 'AND', 'XOR', 'OR', 'CP' ]

# rot and shift instruction table (C++ method names)
rot = [ '_z80_rlc', '_z80_rrc', '_z80_rl', '_z80_rr', '_z80_sla', '_z80_sra', '_z80_sll', '_z80_srl' ]

# the same 'human readbla for comments
rot_cmt = [ 'RLC', 'RRC', 'RL', 'RR', 'SLA', 'SRA', 'SLL', 'SRL' ]

# an 'opcode' wraps the instruction byte, human-readable asm mnemonics,
# and the source code which implements the instruction
class opcode :
    def __init__(self, op) :
        self.byte = op
        self.cmt = None
        self.src = None

#-------------------------------------------------------------------------------
#   Generate code for an opcode fetch. If xxcb_ext is true, the special
#   opcode fetch following a DD/FD+CB prefix instruction is generated
#   which doesn't increment the R register
#
#    instruction fetch machine cycle (M1)
#              T1   T2   T3   T4
#    --------+----+----+----+----+
#    CLK     |--**|--**|--**|--**|
#    A15-A0  |   PC    | REFRESH |
#    MREQ    |   *|****|  **|**  |
#    RD      |   *|****|    |    |
#    WAIT    |    | -- |    |    |
#    M1      |****|****|    |    |
#    D7-D0   |    |   X|    |    |
#    RFSH    |    |    |****|****|
#
def fetch(xxcb_ext):
    src = '/*>fetch*/{'
    # T1
    src += 'c->CTRL|=Z80_M1;c->ADDR=c->PC++;'
    src += tick()
    # T2
    src += 'c->CTRL|=(Z80_MREQ|Z80_RD);'
    src += tick()
    src += 'opcode=c->DATA;'
    # T3
    src += 'c->CTRL&=~(Z80_M1|Z80_MREQ|Z80_RD);'
    if not xxcb_ext:
        src += 'c->R=(c->R&0x80)|((c->R+1)&0x7F);'
    src += 'c->CTRL|=Z80_RFSH;'
    src += tick()
    # T4
    src += 'c->CTRL|=Z80_MREQ;c->ADDR=c->IR;'
    src += tick()
    src += 'c->CTRL&=~(Z80_RFSH|Z80_MREQ);'
    src += '}/*<fetch*/'
    return src

#-------------------------------------------------------------------------------
#   Generate code for a memory-read machine cycle
#
#              T1   T2   T3
#    --------+----+----+----+
#    CLK     |--**|--**|--**|
#    A15-A0  |   MEM ADDR   |
#    MREQ    |   *|****|**  |
#    RD      |   *|****|**  |
#    WR      |    |    |    |
#    D7-D0   |    |    | X  |
#    WAIT    |    | -- |    |
def rd(addr,res):
    src='/*>rd*/'
    # T1
    src+='c->ADDR='+addr+';'
    src+=tick()
    # T2
    src+='c->CTRL|=(Z80_MREQ|Z80_RD);'
    src+=tick()
    src+=res+'=c->DATA;'
    # T3
    src+='c->CTRL&=~(Z80_MREQ|Z80_RD);'
    src+=tick()
    src+='/*<rd*/'
    return src

#-------------------------------------------------------------------------------
#   Generate code for a memory-write machine cycle
#
#              T1   T2   T3
#    --------+----+----+----+
#    CLK     |--**|--**|--**|
#    A15-A0  |   MEM ADDR   |
#    MREQ    |   *|****|**  |
#    RD      |    |    |    |
#    WR      |    |  **|**  |
#    D7-D0   |   X|XXXX|XXXX|
#    WAIT    |    | -- |    |
#
def wr(addr,val):
    src='/*>wr*/'
    # T1
    src+='c->ADDR='+addr+';'
    src+=tick()
    # T2
    src+='c->CTRL|=(Z80_MREQ|Z80_WR);'
    src+='c->DATA='+val+';'
    src+=tick()
    # T3
    src+='c->CTRL&=~(Z80_MREQ|Z80_WR);'
    src+=tick()
    src+='/*wr<*/'
    return src

#-------------------------------------------------------------------------------
#   Generate code for an input machine cycle.
#
#              T1   T2   TW   T3
#    --------+----+----+----+----+
#    CLK     |--**|--**|--**|--**|
#    A15-A0  |     PORT ADDR     |
#    IORQ    |    |****|****|**  |
#    RD      |    |****|****|**  |
#    WR      |    |    |    |    |
#    D7-D0   |    |    |    | X  |
#    WAIT    |    |    | -- |    |
#
#    NOTE: the IORQ|RD pins will already be switched off at the beginning
#    of TW, so that IO devices don't need to do double work.
#
def inp(addr,res):
    src='/*>in*/'
    # T1
    src+='c->ADDR='+addr+';'
    src+=tick()
    # T2
    src+='c->CTRL|=(Z80_IORQ|Z80_RD);'
    src+=tick()
    src+=res+'=c->DATA;'
    # TW+T3
    src+='c->CTRL&=~(Z80_IORQ|Z80_RD);'
    src+=tick(2)
    src+='/*<in*/'
    return src

#-------------------------------------------------------------------------------
#   Generate code for output machine cycle.
#
#              T1   T2   TW   T3
#    --------+----+----+----+----+
#    CLK     |--**|--**|--**|--**|
#    A15-A0  |     PORT ADDR     |
#    IORQ    |    |****|****|**  |
#    RD      |    |    |    |    |
#    WR      |    |****|****|**  |
#    D7-D0   |  XX|XXXX|XXXX|XXXX|
#    WAIT    |    |    | -- |    |
#
#    NOTE: the IORQ|WR pins will already be switched off at the beginning
#    of TW, so that IO devices don't need to do double work.
#
def out(addr,val):
    src='/*>out*/'
    # T1
    src+='c->ADDR='+addr+';'
    src+=tick()
    # T2
    src+='c->CTRL|=(Z80_IORQ|Z80_WR);'
    src+='c->DATA='+val+';'
    src+=tick()
    # TW+T3
    src+='c->CTRL&=~(Z80_IORQ|Z80_WR);'
    src+=tick(2)
    src+='/*<out*/'
    return src

#-------------------------------------------------------------------------------
# return comment string for (HL), (IX+d), (IY+d)
#
def iHLcmt(ext) :
    if (ext) :
        return '('+r[6]+'+d)'
    else :
        return '('+r[6]+')'

#-------------------------------------------------------------------------------
# Return code to setup an address variable 'a' with the address of HL
# or (IX+d), (IY+d). For the index instructions also update WZ with
# IX+d or IY+d
#
def iHLsrc(ext) :
    if (ext) :
        # IX+d or IY+d
        return rd('c->PC++','d')+';a=c->WZ=c->'+r[6]+'+d;'
    else :
        # HL
        return 'a=c->'+r[6]+';'

#-------------------------------------------------------------------------------
# Return code to setup an variable 'a' with the address of HL or (IX+d), (IY+d).
# For the index instructions, also update WZ with IX+d or IY+d
#
def iHLdsrc(ext) :
    if (ext) :
        # IX+d or IY+d
        return 'a=c->WZ=c->'+r[6]+'+d;'
    else :
        # HL
        return 'a=c->'+r[6]+';'

#-------------------------------------------------------------------------------
#   Generate code for one or more 'ticks', call tick callback and increment 
#   the ticks counter.
#
def tick(num=1):
    return 'tick(c);ticks++;'*num

#-------------------------------------------------------------------------------
# Return string with num ticks or empty string depending on 'ext'
#
def ext_ticks(ext, num):
    if ext:
        return tick(num)
    else:
        return ''

#-------------------------------------------------------------------------------
#   imm16()
#
#   Generate code for a 16-bit immediate load into WZ
#
def imm16():
    src =rd('c->PC++','c->Z')
    src+=rd('c->PC++','c->W')
    return src

#-------------------------------------------------------------------------------
#   sz(val)
#
#   Return code to evaluate S and Z flags from value.
#
def sz(val):
    return '(('+val+'&0xFF)?('+val+'&Z80_SF):Z80_ZF)'

#-------------------------------------------------------------------------------
#   out_n_a
#
#   Generate code for OUT (n),A
#
def out_n_a():
    src =rd('c->PC++','v')
    src+='c->WZ=((c->A<<8)|v);'
    src+=out('c->WZ','c->A')
    src+='c->Z++;'
    return src

#-------------------------------------------------------------------------------
#   in_A_n
#
#   Generate code for IN A,(n)
#
def in_n_a():
    src =rd('c->PC++','v')
    src+='c->WZ=((c->A<<8)|v);'
    src+=inp('c->WZ++','c->A')
    return src

#-------------------------------------------------------------------------------
#   ex_sp_dd
#
#   Generate code for EX (SP),HL; EX (SP),IX and EX (SP),IY
#
def ex_sp_dd():
    src =tick()
    src+=rd('c->SP','c->Z')
    src+=rd('c->SP+1','c->W')
    src+=wr('c->SP','(uint8_t)c->'+rp[2])
    src+=wr('c->SP+1','(uint8_t)(c->'+rp[2]+'>>8)')
    src+='c->'+rp[2]+'=c->WZ;'
    src+=tick(2)
    return src

#-------------------------------------------------------------------------------
#   exx
#
#   Generate code for EXX
#
def exx():
    src ='_SWP16(c->BC,c->BC_);'
    src+='_SWP16(c->DE,c->DE_);'
    src+='_SWP16(c->HL,c->HL_);'
    return src

#-------------------------------------------------------------------------------
#   pop_dd
#
#   Generate code for POP dd.
#
def pop_dd(p):
    src =rd('c->SP++','l')
    src+=rd('c->SP++','h')
    src+='c->'+rp2[p]+'=(h<<8)|l;'
    return src

#-------------------------------------------------------------------------------
#   push_dd
#
#   Generate code for PUSH dd
#
def push_dd(p):
    src =tick()
    src+=wr('--c->SP','(uint8_t)(c->'+rp2[p]+'>>8)')
    src+=wr('--c->SP','(uint8_t)c->'+rp2[p])    
    return src

#-------------------------------------------------------------------------------
#   ld_inn_dd
#   LD (nn),dd
#
def ld_inn_dd(p):
    src =imm16()
    src+=wr('c->WZ++','(uint8_t)c->'+rp[p])
    src+=wr('c->WZ','(uint8_t)(c->'+rp[p]+'>>8)')
    return src

#-------------------------------------------------------------------------------
#   ld_dd_inn
#   LD dd,(nn)
#
def ld_dd_inn(p):
    src =imm16()
    src+=rd('c->WZ++','l')
    src+=rd('c->WZ','h')
    src+='c->'+rp[p]+'=(h<<8)|l;'
    return src

#-------------------------------------------------------------------------------
#   rot_idd
#
#   Generate code for ROT (HL); ROT (IX+d); ROT (IY+d)
#
def rot_idd(ext, y):
    src =iHLdsrc(ext)
    src+=tick()
    src+=ext_ticks(ext,1)
    src+=rd('a','v')
    src+=wr('a',rot[y]+'(c,v)')
    return src

#-------------------------------------------------------------------------------
#   rot_idd_r
#
#   Generate code for ROT (IX+d),r; ROT (IY+d),r undocumented instructions.
#
def rot_idd_r(y, z):
    src =iHLdsrc(True)
    src+=tick(2)
    src+=rd('a','v')
    src+='v='+rot[y]+'(c,v);'
    src+='c->'+r2[z]+'=v;'
    src+=wr('a','v')
    return src

#-------------------------------------------------------------------------------
#   bit_n_idd
#
#   Generate code for BIT n,(HL); BIT n,(IX+d); BIT n,(IY+d)
#
#   Flag computation: the undocumented YF and XF flags are set from high byte 
#   of HL+1 or IX/IY+d
#
def bit_n_idd(ext, y):
    src =iHLdsrc(ext)
    src+=tick()
    src+=ext_ticks(ext,1)
    src+=rd('a','v')
    src+='v&='+hex(1<<y)+';'
    src+='f=Z80_HF|(v?(v&Z80_SF):(Z80_ZF|Z80_PF))|(c->W&(Z80_YF|Z80_XF));'
    src+='c->F=f|(c->F&Z80_CF);'
    return src

#-------------------------------------------------------------------------------
#   bit_n_r
#
#   Generate code for BIT n,r
#
def bit_n_r(ext,y,z):
    src ='v=c->'+r2[z]+'&'+hex(1<<y)+';'
    src+='f=Z80_HF|(v?(v&Z80_SF):(Z80_ZF|Z80_PF))|(c->'+r2[z]+'&(Z80_YF|Z80_XF));'
    src+='c->F=f|(c->F&Z80_CF);'
    return src

#-------------------------------------------------------------------------------
#   res_n_idd
#
#   Generate code for RES n,(HL); RES n,(IX+d); RES n,(IY+d)
#
def res_n_idd(ext, y):
    src =iHLdsrc(ext)
    src+=tick()
    src+=ext_ticks(ext,1)
    src+=rd('a','v')
    src+=wr('a','v&~'+hex(1<<y))
    return src

#-------------------------------------------------------------------------------
#   res_n_idd_r
#
#   Generate code for RES n,(IX+d),r; RES n,(IY+d),r undocumented instructions
#
def res_n_idd_r(ext, y, z):
    src =iHLdsrc(ext)
    src+=tick()
    src+=ext_ticks(ext,1)
    src+=rd('a','v')
    src+='c->'+r2[z]+'=v&~'+hex(1<<y)+';'
    src+=wr('a','c->'+r2[z])
    return src

#-------------------------------------------------------------------------------
#   set_n_idd
#
#   Generate code for SET n,(HL); SET n,(IX+d); SET n,(IY+d)
#
def set_n_idd(ext, y):
    src =iHLdsrc(ext)
    src+=tick()
    src+=ext_ticks(ext,1)
    src+=rd('a','v')
    src+=wr('a','v|'+hex(1<<y))
    return src

#-------------------------------------------------------------------------------
#   set_n_idd_r
#
#   Generate code for SET n,(IX+d),r; SET n,(IY+d),r undocumented instructions
#
def set_n_idd_r(ext, y, z):
    src =iHLdsrc(ext)
    src+=tick()
    src+=ext_ticks(ext,1)
    src+=rd('a','v')
    src+='c->'+r2[z]+'=v|'+hex(1<<y)+';'
    src+=wr('a','c->'+r2[z])
    return src

#-------------------------------------------------------------------------------
#   call_nn
#
#   Generate code for CALL nn
#
def call_nn():
    src =imm16()
    src+=tick()
    src+=wr('--c->SP','(uint8_t)(c->PC>>8)')
    src+=wr('--c->SP','(uint8_t)c->PC')
    src+='c->PC=c->WZ;'
    return src

#-------------------------------------------------------------------------------
#   call_cc_nn
#
#   Generate code for CALL cc,nn
#
def call_cc_nn(y):
    src =imm16()
    src+='if ('+cond[y]+'){'
    src+=tick()
    src+=wr('--c->SP','(uint8_t)(c->PC>>8)')
    src+=wr('--c->SP','(uint8_t)c->PC')
    src+='c->PC=c->WZ;'
    src+='}'
    return src

#-------------------------------------------------------------------------------
#   rrd
#
def rrd():
    src ='c->WZ=c->HL;'
    src+=rd('c->WZ++','v')
    src+='l=c->A&0x0F;'
    src+='c->A=(c->A&0xF0)|(v&0x0F);'
    src+='v=(v>>4)|(l<<4);'
    src+=tick(4)
    src+=wr('c->HL','v')
    src+='c->F=c->szp[c->A]|(c->F&Z80_CF);'
    return src

#-------------------------------------------------------------------------------
#   rld
#
def rld():
    src ='c->WZ=c->HL;'
    src+=rd('c->WZ++','v')
    src+='l=c->A&0x0F;'
    src+='c->A=(c->A&0xF0)|(v>>4);'
    src+='v=(v<<4)|l;'
    src+=tick(4)
    src+=wr('c->HL','v')
    src+='c->F=c->szp[c->A]|(c->F&Z80_CF);'
    return src

#-------------------------------------------------------------------------------
#   ldi
#
def ldi():
    src =rd('c->HL','v')
    src+=wr('c->DE','v')
    src+=tick(2)
    src+='v+=c->A;'
    src+='f=c->F&(Z80_SF|Z80_ZF|Z80_CF);'
    src+='if(v&0x02){f|=Z80_YF;}'
    src+='if(v&0x08){f|=Z80_XF;}'
    src+='c->HL++;c->DE++;c->BC--;'
    src+='if(c->BC){f|=Z80_VF;}'
    src+='c->F=f;'
    return src

#-------------------------------------------------------------------------------
#   ldir
#
def ldir():
    src=ldi()
    src+='if(c->BC){'
    src+='c->PC-=2;'
    src+='c->WZ=c->PC+1;'
    src+=tick(5)
    src+='}'
    return src

#-------------------------------------------------------------------------------
#   ldd
#
def ldd():
    src =rd('c->HL','v')
    src+=wr('c->DE','v')
    src+=tick(2)
    src+='v+=c->A;'
    src+='f=c->F&(Z80_SF|Z80_ZF|Z80_CF);'
    src+='if(v&0x02){f|=Z80_YF;}'
    src+='if(v&0x08){f|=Z80_XF;}'
    src+='c->HL--;c->DE--;c->BC--;'
    src+='if(c->BC){f|=Z80_VF;}'
    src+='c->F=f;'
    return src

#-------------------------------------------------------------------------------
#   lddr()
#
def lddr():
    src =ldd()
    src+='if(c->BC){'
    src+='c->PC-=2;'
    src+='c->WZ=c->PC+1;'
    src+=tick(5)
    src+='}'
    return src

#-------------------------------------------------------------------------------
#   cpi()
#
def cpi():
    src =rd('c->HL','v')
    src+=tick(5)
    src+='{int r=(int)c->A-v;'
    src+='f=Z80_NF|(c->F&Z80_CF)|'+sz('r')+';'
    src+='if((r&0x0F)>(c->A&0x0F)){'
    src+='f|=Z80_HF;'
    src+='r--;'
    src+='}'
    src+='if(r&0x02){f|=Z80_YF;}'
    src+='if(r&0x08){f|=Z80_XF;}'
    src+='}'
    src+='c->WZ++;c->HL++;c->BC--;'
    src+='if(c->BC){f|=Z80_VF;}'
    src+='c->F=f;'
    return src

#-------------------------------------------------------------------------------
#   cpir()
#
def cpir():
    src =cpi()
    src+='if(c->BC&&!(c->F&Z80_ZF)){'
    src+='c->PC-=2;'
    src+='c->WZ=c->PC+1;'   # FIXME: is this correct (see memptr_eng.txt)
    src+=tick(5)
    src+='}'
    return src

#-------------------------------------------------------------------------------
#   cpd()
#
def cpd():
    src =rd('c->HL','v')
    src+='{int r=(int)c->A-v;'
    src+=tick(5)
    src+='f=Z80_NF|(c->F&Z80_CF)|'+sz('r')+';'
    src+='if((r&0x0F)>(c->A&0x0F)){'
    src+='f|=Z80_HF;'
    src+='r--;'
    src+='}'
    src+='if(r&0x02){f|=Z80_YF;}'
    src+='if(r&0x08){f|=Z80_XF;}'
    src+='}'
    src+='c->WZ--;c->HL--;c->BC--;'
    src+='if(c->BC){f|=Z80_VF;}'
    src+='c->F=f;'
    return src

#-------------------------------------------------------------------------------
#   cpdr()
#
def cpdr():
    src =cpd()
    src+='if((c->BC)&&!(c->F&Z80_ZF)){'
    src+='c->PC-=2;'
    src+='c->WZ=c->PC+1;'
    src+=tick(5)
    src+='}'
    return src

#-------------------------------------------------------------------------------
#   ini_ind_flags(io_val,c_add)
#   outi_outd_flags(io_val,c_add)
#
#   Returns a string which evaluates the flags for ini and ind instructions into F.
#   NOTE: most INI/OUTI flag settings are undocumented in the official
#   docs, so this is taken from MAME, there's also more
#   information here: http://www.z80.info/z80undoc3.txt
#
def ini_ind_flags(io_val,c_add):
    src ='f=c->B?(c->B&Z80_SF):Z80_ZF;'
    src+='if('+io_val+'&Z80_SF){f|=Z80_NF;}'
    src+='{';
    src+='uint32_t t=(uint32_t)((c->C+('+c_add+'))&0xFF)+(uint32_t)'+io_val+';'
    src+='if(t&0x100){f|=(Z80_HF|Z80_CF);}'
    src+='f|=c->szp[((uint8_t)(t&0x07))^c->B]&Z80_PF;'
    src+='}'
    src+='c->F=f;'
    return src

def outi_outd_flags(io_val):
    src='f=c->B?(c->B&Z80_SF):Z80_ZF;'
    src+='if('+io_val+'&Z80_SF){f|=Z80_NF;}'
    src+='{';
    src+='uint32_t t=(uint32_t)c->L+(uint32_t)'+io_val+';'
    src+='if(t&0x100){f|=(Z80_HF|Z80_CF);}'
    src+='f|=c->szp[((uint8_t)(t&0x07))^c->B]&Z80_PF;'
    src+='}'
    src+='c->F=f;'
    return src

#-------------------------------------------------------------------------------
#   ini()
#
def ini():
    src =tick()
    src+='c->WZ=c->BC;'
    src+=inp('c->WZ++','v')
    src+='c->B--;'
    src+=wr('c->HL++','v')
    src+=ini_ind_flags('v','+1')
    return src

#-------------------------------------------------------------------------------
#   inir()
#
def inir():
    src =ini()
    src+='if(c->B){'
    src+='c->PC-=2;'
    src+=tick(5)
    src+='}'
    return src

#-------------------------------------------------------------------------------
#   ind()
#
def ind():
    src =tick()
    src+='c->WZ=c->BC;'
    src+=inp('c->WZ--','v')
    src+='c->B--;'
    src+=wr('c->HL--','v')
    src+=ini_ind_flags('v','-1')
    return src

#-------------------------------------------------------------------------------
#   indr()
#
def indr():
    src =ind()
    src+='if(c->B){'
    src+='c->PC-=2;'
    src+=tick(5)
    src+='}'
    return src

#-------------------------------------------------------------------------------
#   outi()
#
def outi():
    src =tick()
    src+=rd('c->HL++','v')
    src+='c->B--;'
    src+='c->WZ=c->BC;'
    src+=out('c->WZ++','v')
    src+=outi_outd_flags('v')
    return src

#-------------------------------------------------------------------------------
#   otir()
#
def otir():
    src =outi()
    src+='if(c->B){'
    src+='c->PC-=2;'
    src+=tick(5)
    src+='}'
    return src

#-------------------------------------------------------------------------------
#   outd()
#
def outd():
    src =tick()
    src+=rd('c->HL--','v')
    src+='c->B--;'
    src+='c->WZ=c->BC;'
    src+=out('c->WZ--','v')
    src+=outi_outd_flags('v')
    return src

#-------------------------------------------------------------------------------
#   otdr()
#
def otdr():
    src =outd()
    src+='if(c->B){'
    src+='c->PC-=2;'
    src+=tick(5)
    src+='}'
    return src

#-------------------------------------------------------------------------------
#   djnz()
#
def djnz():
    src =tick()
    src+=rd('c->PC++','d')
    src+='if(--c->B>0){'
    src+='c->WZ=c->PC=c->PC+d;'
    src+=tick(5)
    src+='}'
    return src

#-------------------------------------------------------------------------------
#   jr()
#
def jr():
    src =rd('c->PC++','d')
    src+='c->WZ=c->PC=c->PC+d;'
    src+=tick(5)
    return src;

#-------------------------------------------------------------------------------
#   jr_cc()
#
def jr_cc(y):
    src =rd('c->PC++','d')
    src+='if('+cond[y-4]+'){'
    src+='c->WZ=c->PC=c->PC+d;'
    src+=tick(5)
    src+='}'
    return src

#-------------------------------------------------------------------------------
#   ret()
#
def ret():
    src =rd('c->SP++','c->Z')
    src+=rd('c->SP++','c->W')
    src+='c->PC=c->WZ;'
    return src

#-------------------------------------------------------------------------------
#   ret_cc()
#
def ret_cc(y):
    src =tick()
    src+='if('+cond[y]+'){'
    src+=rd('c->SP++','c->Z')
    src+=rd('c->SP++','c->W')
    src+='c->PC=c->WZ;'
    src+='}'
    return src

#-------------------------------------------------------------------------------
#   rst()
#
def rst(y):
    src =wr('--c->SP','(uint8_t)c->PC<<8')
    src+=wr('--c->SP','(uint8_t)c->PC')
    src+='c->WZ=c->PC=(uint16_t)'+hex(y*8)+';'
    return src

#-------------------------------------------------------------------------------
#   in_ic()
#   IN (C)
#
def in_ic():
    src ='c->WZ=c->BC;'
    src+=inp('c->WZ++','v')
    src+='c->F=c->szp[v]|(c->F&Z80_CF);'
    return src

#-------------------------------------------------------------------------------
#   in_r_ic
#   IN r,(C)
#
def in_r_ic(y):
    src ='c->WZ=c->BC;'
    src+=inp('c->WZ++','c->'+r[y])
    src+='c->F=c->szp[c->'+r[y]+']|(c->F&Z80_CF);'
    return src

#-------------------------------------------------------------------------------
#   out_ic()
#   OUT (C)
#
def out_ic():
    src ='c->WZ=c->BC;'
    src+=out('c->WZ++','0')
    return src

#-------------------------------------------------------------------------------
#   out_r_ic()
#   OUT r,(C)
#
def out_r_ic(y):
    src ='c->WZ=c->BC;'
    src+=out('c->WZ++','c->'+r[y])
    return src

#-------------------------------------------------------------------------------
#   ALU funcs
#
def add8(val):
    src ='{'
    src+='int res=c->A+'+val+';'
    src+='c->F=_ADD_FLAGS(c->A,'+val+',res);'
    src+='c->A=(uint8_t)res;'
    src+='}'
    return src

def adc8(val):
    src ='{'
    src+='int res=c->A+'+val+'+(c->F&Z80_CF);'
    src+='c->F=_ADD_FLAGS(c->A,'+val+',res);'
    src+='c->A=(uint8_t)res;'
    src+='}'
    return src

def sub8(val):
    src ='{'
    src+='int res=(int)c->A-(int)'+val+';'
    src+='c->F=_SUB_FLAGS(c->A,'+val+',res);'
    src+='c->A=(uint8_t)res;'
    src+='}'
    return src

def sbc8(val):
    src ='{'
    src+='int res=(int)c->A-(int)'+val+'-(c->F&Z80_CF);'
    src+='c->F=_SUB_FLAGS(c->A,'+val+',res);'
    src+='c->A=(uint8_t)res;'
    src+='}'
    return src

def cp8(val):
    # NOTE: XF|YF are set from val, not from result
    src ='{'
    src+='int res=(int)c->A-(int)'+val+';'
    src+='c->F=_CP_FLAGS(c->A,'+val+',res);'
    src+='}'
    return src

def and8(val):
    src='c->A&='+val+';c->F=c->szp[c->A]|Z80_HF;' 
    return src

def or8(val):
    src='c->A|='+val+';c->F=c->szp[c->A];' 
    return src

def xor8(val):
    src='c->A^='+val+';c->F=c->szp[c->A];' 
    return src

def alu8(y,val):
    if (y==0):
        return add8(val)
    elif (y==1):
        return adc8(val)
    elif (y==2):
        return sub8(val)
    elif (y==3):
        return sbc8(val)
    elif (y==4):
        return and8(val)
    elif (y==5):
        return xor8(val)
    elif (y==6):
        return or8(val)
    elif (y==7):
        return cp8(val)

def neg8():
    src ='v=c->A;c->A=0;'
    src+=sub8('v')
    return src

def inc8(val):
    src ='{'
    src+='uint8_t r='+val+'+1;'
    src+='f=_SZ(r)|(r&(Z80_XF|Z80_YF))|((r^'+val+')&Z80_HF);'
    src+='if(r==0x80){f|=Z80_VF;}'
    src+='c->F=f|(c->F&Z80_CF);'
    src+=val+'=r;'
    src+='}'
    return src

def dec8(val):
    src ='{'
    src+='uint8_t r='+val+'-1;'
    src+='f=Z80_NF|_SZ(r)|(r&(Z80_XF|Z80_YF))|((r^'+val+')&Z80_HF);'
    src+='if(r==0x7F){f|=Z80_VF;}'
    src+='c->F=f|(c->F&Z80_CF);'
    src+=val+'=r;'
    src+='}'
    return src

#-------------------------------------------------------------------------------
#   16-bit add,adc,sbc
#
#   flags computation taken from MAME
#
def add16(acc,val):
    src ='{'
    src+='c->WZ='+acc+'+1;'
    src+='uint32_t r='+acc+'+'+val+';'
    src+='c->F=(c->F&(Z80_SF|Z80_ZF|Z80_VF))|'
    src+='((('+acc+'^r^'+val+')>>8)&Z80_HF)|'
    src+='((r>>16)&Z80_CF)|((r>>8)&(Z80_YF|Z80_XF));'
    src+=acc+'=r;'
    src+='}'
    return src

def adc16(acc,val):
    src ='{'
    src+='c->WZ='+acc+'+1;'
    src+='uint32_t r='+acc+'+'+val+'+(c->F&Z80_CF);'
    src+='c->F=((('+acc+'^r^'+val+')>>8)&Z80_HF)|'
    src+='((r>>16)&Z80_CF)|'
    src+='((r>>8)&(Z80_SF|Z80_YF|Z80_XF))|'
    src+='((r&0xFFFF)?0:Z80_ZF)|'
    src+='((('+val+'^'+acc+'^0x8000)&('+val+'^r)&0x8000)>>13);'
    src+=acc+'=r;'
    src+='}'
    return src

def sbc16(acc,val):
    src ='{'
    src+='c->WZ='+acc+'+1;'
    src+='uint32_t r='+acc+'-'+val+'-(c->F&Z80_CF);'
    src+='c->F=((('+acc+'^r^'+val+')>>8)&Z80_HF)|Z80_NF|'
    src+='((r>>16)&Z80_CF)|'
    src+='((r>>8)&(Z80_SF|Z80_YF|Z80_XF))|'
    src+='((r&0xFFFF)?0:Z80_ZF)|'
    src+='((('+val+'^'+acc+')&('+acc+'^r)&0x8000)>>13);'
    src+=acc+'=r;'
    src+='}'
    return src

#-------------------------------------------------------------------------------
#   misc ops
#
def cpl():
    src ='c->A^=0xFF;'
    src+='c->F=(c->F&(Z80_SF|Z80_ZF|Z80_PF|Z80_CF))|Z80_HF|Z80_NF|(c->A&(Z80_YF|Z80_XF));'
    return src

def scf():
    return 'c->F=(c->F&(Z80_SF|Z80_ZF|Z80_YF|Z80_XF|Z80_PF))|Z80_CF|(c->A&(Z80_YF|Z80_XF));'

def ccf():
    return 'c->F=((c->F&(Z80_SF|Z80_ZF|Z80_YF|Z80_XF|Z80_PF|Z80_CF))|((c->F&Z80_CF)<<4)|(c->A&(Z80_YF|Z80_XF)))^Z80_CF;'

# DAA from MAME and http://www.z80.info/zip/z80-documented.pdf
def daa():
    src ='v=c->A;'
    src+='if(c->F&Z80_NF){'
    src+='if(((c->A&0xF)>0x9)||(c->F&Z80_HF)){v-=0x06;}'
    src+='if((c->A>0x99)||(c->F&Z80_CF)){v-=0x60;}'
    src+='}else{'
    src+='if(((c->A&0xF)>0x9)||(c->F&Z80_HF)){v+=0x06;}'
    src+='if((c->A>0x99)||(c->F&Z80_CF)){v+=0x60;}'
    src+='}'
    src+='c->F&=Z80_CF|Z80_NF;'
    src+='c->F|=(c->A>0x99)?Z80_CF:0;'
    src+='c->F|=(c->A^v)&Z80_HF;'
    src+='c->F|=c->szp[v];'
    src+='c->A=v;'
    return src

#-------------------------------------------------------------------------------
# Encode a main instruction, or an DD or FD prefix instruction.
# Takes an opcode byte and returns an opcode object, for invalid instructions
# the opcode object will be in its default state (opcode.src==None).
# cc is the name of the cycle-count table.
#
def enc_op(op, ext, cc) :

    o = opcode(op)

    # split opcode byte into bit groups, these identify groups
    # or subgroups of instructions, or serve as register indices 
    #
    #   |xx|yyy|zzz|
    #   |xx|pp|q|zzz|
    x = op>>6
    y = (op>>3)&7
    z = op&7
    p = y>>1
    q = y&1

    #---- block 1: 8-bit loads, and HALT
    if x == 1:
        if y == 6:
            if z == 6:
                # special case: LD (HL),(HL) is HALT
                o.cmt = 'HALT'
                o.src = '_z80_halt(c);'
            else:
                # LD (HL),r; LD (IX+d),r; LD (IX+d),r
                o.cmt = 'LD '+iHLcmt(ext)+','+r2[z]
                o.src = iHLsrc(ext)+ext_ticks(ext,5)+wr('a','c->'+r2[z])
        elif z == 6:
            # LD r,(HL); LD r,(IX+d); LD r,(IY+d)
            o.cmt = 'LD '+r2[y]+','+iHLcmt(ext)
            o.src = iHLsrc(ext)+ext_ticks(ext,5)+rd('a','c->'+r2[y])
        else:
            # LD r,s
            o.cmt = 'LD '+r[y]+','+r[z]
            o.src = 'c->'+r[y]+'=c->'+r[z]+';'

    #---- block 2: 8-bit ALU instructions (ADD, ADC, SUB, SBC, AND, XOR, OR, CP)
    elif x == 2:
        if z == 6:
            # ALU (HL); ALU (IX+d); ALU (IY+d)
            o.cmt = alu_cmt[y]+' '+iHLcmt(ext)
            o.src = iHLsrc(ext)+ext_ticks(ext,5)+rd('a','v')+alu8(y,'v')
        else:
            # ALU r
            o.cmt = alu_cmt[y]+' '+r[z]
            o.src = alu8(y,'c->'+r[z])

    #---- block 0: misc ops
    elif x == 0:
        if z == 0:
            if y == 0:
                # NOP
                o.cmt = 'NOP'
                o.src = ' '
            elif y == 1:
                # EX AF,AF'
                o.cmt = "EX AF,AF'"
                o.src = '_SWP16(c->AF,c->AF_);'
            elif y == 2:
                # DJNZ d
                o.cmt = 'DJNZ'
                o.src = djnz()
            elif  y == 3:
                # JR d
                o.cmt = 'JR d'
                o.src = jr()
            else:
                # JR cc,d
                o.cmt = 'JR '+cond_cmt[y-4]+',d'
                o.src = jr_cc(y)
        elif z == 1:
            if q == 0:
                # 16-bit immediate loads
                o.cmt = 'LD '+rp[p]+',nn'
                o.src = imm16()+'c->'+rp[p]+'=c->WZ;'
            else :
                # ADD HL,rr; ADD IX,rr; ADD IY,rr
                o.cmt = 'ADD '+rp[2]+','+rp[p]
                o.src = add16('c->'+rp[2],'c->'+rp[p])+tick(7)
        elif z == 2:
            # indirect loads
            op_tbl = [
                [ 'LD (BC),A', 'c->WZ=c->BC;'+wr('c->WZ++','c->A')+';c->W=c->A;' ],
                [ 'LD A,(BC)', 'c->WZ=c->BC;'+rd('c->WZ++','c->A')+';' ],
                [ 'LD (DE),A', 'c->WZ=c->DE;'+wr('c->WZ++','c->A')+';c->W=c->A;' ],
                [ 'LD A,(DE)', 'c->WZ=c->DE;'+rd('c->WZ++','c->A')+';' ],
                [ 'LD (nn),'+rp[2], imm16()+wr('c->WZ++','(uint8_t)c->'+rp[2])+wr('c->WZ','(uint8_t)(c->'+rp[2]+'>>8)') ],
                [ 'LD '+rp[2]+',(nn)', imm16()+rd('c->WZ++','l')+rd('c->WZ','h')+'c->'+rp[2]+'=(h<<8)|l;' ],
                [ 'LD (nn),A', imm16()+wr('c->WZ++','c->A')+';c->W=c->A;' ],
                [ 'LD A,(nn)', imm16()+rd('c->WZ++','c->A')+';' ]
            ]
            o.cmt = op_tbl[y][0]
            o.src = op_tbl[y][1]
        elif z == 3:
            # 16-bit INC/DEC 
            if q == 0:
                o.cmt = 'INC '+rp[p]
                o.src = tick(2)+'c->'+rp[p]+'++;'.format(rp[p])
            else:
                o.cmt = 'DEC '+rp[p]
                o.src = tick(2)+'c->'+rp[p]+'--;'.format(rp[p])
        elif z == 4 or z == 5:
            cmt = 'INC' if z == 4 else 'DEC'
            if y == 6:
                # INC/DEC (HL)/(IX+d)/(IY+d)
                o.cmt = cmt+' '+iHLcmt(ext)
                fn = inc8('v') if z==4 else dec8('v')
                o.src = iHLsrc(ext)+ext_ticks(ext,5)+tick()+rd('a','v')+fn+wr('a','v')
            else:
                # INC/DEC r
                o.cmt = cmt+' '+r[y]
                o.src = inc8('c->'+r[y]) if z==4 else dec8('c->'+r[y])
        elif z == 6:
            if y == 6:
                # LD (HL),n; LD (IX+d),n; LD (IY+d),n
                o.cmt = 'LD '+iHLcmt(ext)+',n'
                o.src = iHLsrc(ext)+ext_ticks(ext,2)+rd('c->PC++','v')+wr('a','v')
            else:
                # LD r,n
                o.cmt = 'LD '+r[y]+',n'
                o.src = rd('c->PC++','c->'+r[y])
        elif z == 7:
            # misc ops on A and F
            op_tbl = [
                [ 'RLCA', '_z80_rlca(c);'],
                [ 'RRCA', '_z80_rrca(c);'],
                [ 'RLA',  '_z80_rla(c);'],
                [ 'RRA',  '_z80_rra(c);'],
                [ 'DAA',  daa() ],
                [ 'CPL',  cpl() ],
                [ 'SCF',  scf() ],
                [ 'CCF',  ccf() ]
            ]
            o.cmt = op_tbl[y][0]
            o.src = op_tbl[y][1]

    #--- block 3: misc and extended ops
    elif x == 3:
        if z == 0:
            # RET cc
            o.cmt = 'RET '+cond_cmt[y]
            o.src = ret_cc(y)
        elif z == 1:
            if q == 0:
                # POP BC,DE,HL,IX,IY,AF
                o.cmt = 'POP '+rp2[p]
                o.src = pop_dd(p)
            else:
                # misc ops
                op_tbl = [
                    [ 'RET', ret() ],
                    [ 'EXX', exx() ],
                    [ 'JP '+rp[2], 'c->PC=c->'+rp[2]+';' ],
                    [ 'LD SP,'+rp[2], tick(2)+'c->SP=c->'+rp[2]+';' ]
                ]
                o.cmt = op_tbl[p][0]
                o.src = op_tbl[p][1]
        elif z == 2:
            # JP cc,nn
            o.cmt = 'JP {},nn'.format(cond_cmt[y])
            o.src = imm16()+'if ({}) {{ c->PC=c->WZ; }}'.format(cond[y])
        elif z == 3:
            # misc ops
            op_tbl = [
                [ 'JP nn', imm16()+'c->PC=c->WZ;' ],
                [ None, None ], # CB prefix instructions
                [ 'OUT (n),A', out_n_a() ],
                [ 'IN A,(n)', in_n_a() ],
                [ 'EX (SP),'+rp[2], ex_sp_dd() ],
                [ 'EX DE,HL', '_SWP16(c->DE,c->HL);' ],
                [ 'DI', '_z80_di(c);' ],
                [ 'EI', '_z80_ei(c);' ]
            ]
            o.cmt = op_tbl[y][0]
            o.src = op_tbl[y][1]
        elif z == 4:
            # CALL cc,nn
            o.cmt = 'CALL {},nn'.format(cond_cmt[y])
            o.src = call_cc_nn(y)
        elif z == 5:
            if q == 0:
                # PUSH BC,DE,HL,IX,IY,AF
                o.cmt = 'PUSH {}'.format(rp2[p])
                o.src = push_dd(p)
            else:
                op_tbl = [
                    [ 'CALL nn', call_nn() ],
                    [ None, None ], # DD prefix instructions
                    [ None, None ], # ED prefix instructions
                    [ None, None ], # FD prefix instructions
                ]
                o.cmt = op_tbl[p][0]
                o.src = op_tbl[p][1]
        elif z == 6:
            # ALU n
            o.cmt = '{} n'.format(alu_cmt[y])
            o.src = rd('c->PC++','v')+alu8(y,'v')
        elif z == 7:
            # RST
            o.cmt = 'RST {}'.format(hex(y*8))
            o.src = rst(y)

    return o

#-------------------------------------------------------------------------------
#   ED prefix instructions
#
def enc_ed_op(op) :
    o = opcode(op)
    cc = 'cc_ed'

    x = op>>6
    y = (op>>3)&7
    z = op&7
    p = y>>1
    q = y&1

    if x == 2:
        # block instructions (LDIR etc)
        if y >= 4 and z < 4 :
            op_tbl = [
                [ 
                    [ 'LDI',  ldi() ],
                    [ 'LDD',  ldd() ],
                    [ 'LDIR', ldir() ],
                    [ 'LDDR', lddr() ]
                ],
                [
                    [ 'CPI',  cpi() ],
                    [ 'CPD',  cpd() ],
                    [ 'CPIR', cpir() ],
                    [ 'CPDR', cpdr() ]
                ],
                [
                    [ 'INI',  ini() ],
                    [ 'IND',  ind() ],
                    [ 'INIR', inir() ],
                    [ 'INDR', indr() ]
                ],
                [
                    [ 'OUTI', outi() ],
                    [ 'OUTD', outd() ],
                    [ 'OTIR', otir() ],
                    [ 'OTDR', otdr() ]
                ]
            ]
            o.cmt = op_tbl[z][y-4][0]
            o.src = op_tbl[z][y-4][1]

    elif x == 1:
        # misc ops
        if z == 0:
            # IN r,(C)
            if y == 6:
                # undocumented special case 'IN F,(C)', only alter flags, don't store result
                o.cmt = 'IN (C)';
                o.src = in_ic()
            else:
                o.cmt = 'IN {},(C)'.format(r[y])
                o.src = in_r_ic(y)
        elif z == 1:
            # OUT (C),r
            if y == 6:
                # undocumented special case 'OUT (C),F', always output 0
                o.cmd = 'OUT (C)';
                o.src = out_ic()
            else:
                o.cmt = 'OUT (C),{}'.format(r[y])
                o.src = out_r_ic(y)
        elif z == 2:
            # SBC/ADC HL,rr
            if q==0:
                o.cmt = 'SBC HL,'+rp[p]
                o.src = sbc16('c->HL','c->'+rp[p])+tick(7)
            else:
                o.cmt = 'ADC HL,'+rp[p]
                o.src = adc16('c->HL','c->'+rp[p])+tick(7)
        elif z == 3:
            # 16-bit immediate address load/store
            if q == 0:
                o.cmt = 'LD (nn),{}'.format(rp[p])
                o.src = ld_inn_dd(p)
            else:
                o.cmt = 'LD {},(nn)'.format(rp[p])
                o.src = ld_dd_inn(p)
        elif z == 4:
            # NEG
            o.cmt = 'NEG'
            o.src = neg8()
        elif z == 5:
            # RETN, RETI (only RETI implemented!)
            if y == 1:
                o.cmt = 'RETI'
                o.src = '_z80_reti(c);'
        elif z == 6:
            # IM m
            im_mode = [ 0, 0, 1, 2, 0, 0, 1, 2 ]
            o.cmt = 'IM {}'.format(im_mode[y])
            o.src = 'c->IM={};'.format(im_mode[y])
        elif z == 7:
            # misc ops on I,R and A
            op_tbl = [
                [ 'LD I,A', tick()+'c->I=c->A;' ],
                [ 'LD R,A', tick()+'c->R=c->A;' ],
                [ 'LD A,I', tick()+'c->A=c->I; c->F=_z80_sziff2(c,c->I)|(c->F&Z80_CF);' ],
                [ 'LD A,R', tick()+'c->A=c->R; c->F=_z80_sziff2(c,c->R)|(c->F&Z80_CF);' ],
                [ 'RRD', rrd() ],
                [ 'RLD', rld() ],
                [ 'NOP (ED)', ' ' ],
                [ 'NOP (ED)', ' ' ],
            ]
            o.cmt = op_tbl[y][0]
            o.src = op_tbl[y][1]
    return o

#-------------------------------------------------------------------------------
#   CB prefix instructions
#
def enc_cb_op(op, ext, cc) :
    o = opcode(op)

    x = op>>6
    y = (op>>3)&7
    z = op&7

    if x == 0:
        # rotates and shifts
        if z == 6:
            # ROT (HL); ROT (IX+d); ROT (IY+d)
            o.cmt = '{} {}'.format(rot_cmt[y],iHLcmt(ext))
            o.src = rot_idd(ext,y)
        elif ext:
            # undocumented: ROT (IX+d),(IY+d),r (also stores result in a register)
            o.cmt = '{} {},{}'.format(rot_cmt[y],iHLcmt(ext),r2[z])
            o.src = rot_idd_r(y,z) 
        else:
            # ROT r
            o.cmt = '{} {}'.format(rot_cmt[y],r2[z])
            o.src = 'c->{}={}(c,c->{});'.format(r2[z], rot[y], r2[z])
    elif x == 1:
        # BIT n
        if z == 6 or ext:
            # BIT n,(HL); BIT n,(IX+d); BIT n,(IY+d)
            o.cmt = 'BIT {},{}'.format(y,iHLcmt(ext))
            o.src = bit_n_idd(ext,y) 
        else:
            # BIT n,r
            o.cmt = 'BIT {},{}'.format(y,r2[z])
            o.src = bit_n_r(ext,y,z)
    elif x == 2:
        # RES n
        if z == 6:
            # RES n,(HL); RES n,(IX+d); RES n,(IY+d)
            o.cmt = 'RES {},{}'.format(y,iHLcmt(ext))
            o.src = res_n_idd(ext,y)
        elif ext:
            # undocumented: RES n,(IX+d),r; RES n,(IY+d),r
            o.cmt = 'RES {},{},{}'.format(y,iHLcmt(ext),r2[z])
            o.src = res_n_idd_r(ext,y,z)
        else:
            # RES n,r
            o.cmt = 'RES {},{}'.format(y,r2[z])
            o.src = 'c->{}&=~{};'.format(r2[z], hex(1<<y))
    elif x == 3:
        # SET n
        if z == 6:
            # SET n,(HL); RES n,(IX+d); RES n,(IY+d)
            o.cmt = 'SET {},{}'.format(y,iHLcmt(ext))
            o.src = set_n_idd(ext,y)
        elif ext:
            # undocumented: SET n,(IX+d),r; SET n,(IY+d),r
            o.cmt = 'SET {},{},{}'.format(y,iHLcmt(ext),r2[z])
            o.src = set_n_idd_r(ext,y,z)
        else:
            # SET n,r
            o.cmt = 'SET {},{}'.format(y,r2[z])
            o.src = 'c->{}|={};'.format(r2[z], hex(1<<y))
    return o

#-------------------------------------------------------------------------------
# patch register lookup tables for IX or IY instructions
#
def patch_reg_tables(reg) :
    r[4] = reg+'H'; r[5] = reg+'L'; r[6] = reg;
    rp[2] = rp2[2] = reg

#-------------------------------------------------------------------------------
# 'unpatch' the register lookup tables
#
def unpatch_reg_tables() :
    r[4] = 'H'; r[5] = 'L'; r[6] = 'HL'
    rp[2] = rp2[2] = 'HL'

#-------------------------------------------------------------------------------
# return a tab-string for given indent level
#
def tab(indent) :
    return ' '*TabWidth*indent

#-------------------------------------------------------------------------------
# output a src line
def l(s) :
    Out.write(s+'\n')

#-------------------------------------------------------------------------------
# write source header
#
def write_header() :
    l('// machine generated, do not edit!')
    l('static uint32_t _z80_op(z80* c, uint32_t ticks) {')
    l('  void(*tick)(z80*) = c->tick;')
    l('  uint8_t opcode; int8_t d; uint16_t a; uint8_t v; uint8_t l; uint8_t h; uint8_t f;')

#-------------------------------------------------------------------------------
# begin a new instruction group (begins a switch statement)
#
def write_begin_group(indent, ext_byte=None, xxcb_ext=False) :
    if ext_byte:
        # this is a prefix instruction, need to write a case
        l(tab(indent)+'case '+hex(ext_byte)+':')
    indent += 1
    # xxcb_ext: special case for DD/FD CB 'double extended' instructions,
    # these have the d offset after the CB byte and before
    # the actual instruction byte, and the next opcode fetch doesn't
    # increment R
    if xxcb_ext:
        l(tab(indent)+rd('c->PC++', 'd'))
    l(tab(indent)+fetch(xxcb_ext))
    l(tab(indent)+'switch (opcode) {')
    indent += 1
    return indent

#-------------------------------------------------------------------------------
# write a single (writes a case inside the current switch)
#
def write_op(indent, op) :
    if op.src :
        if not op.cmt:
            op.cmt='???'
        l(tab(indent)+'case '+hex(op.byte)+':/*'+op.cmt+'*/'+op.src+'return ticks;')

#-------------------------------------------------------------------------------
# finish an instruction group (ends current statement)
#
def write_end_group(indent, inv_op_bytes, ext_byte=None) :
    l(tab(indent)+'default: return ticks;')
    indent -= 1
    l(tab(indent)+'}')
    # if this was a prefix instruction, need to write a final break
    if ext_byte:
        l(tab(indent)+'break;')
    indent -= 1
    return indent

#-------------------------------------------------------------------------------
# write source footer
#
def write_footer() :
    l('  return ticks;')
    l('}')

#-------------------------------------------------------------------------------
# main encoder function, this populates all the opcode tables and
# generates the C++ source code into the file f
#
Out = open(OutPath, 'w')
write_header()

# loop over all instruction bytes
indent = write_begin_group(0)
for i in range(0, 256) :
    # DD or FD prefix instruction?
    if i == 0xDD or i == 0xFD:
        indent = write_begin_group(indent, i)
        patch_reg_tables('IX' if i==0xDD else 'IY')
        cc_ix_table = 'cc_dd' if i==0xDD else 'cc_fd'
        cc_ixcb_table = 'cc_ddcb' if i==0xDD else 'cc_fdcb'
        for ii in range(0, 256) :
            if ii == 0xCB:
                # DD/FD CB prefix
                indent = write_begin_group(indent, ii, True)
                for iii in range(0, 256) :
                    write_op(indent, enc_cb_op(iii, True, cc_ixcb_table))
                indent = write_end_group(indent, 4, True)
            else:
                write_op(indent, enc_op(ii, True, cc_ix_table))
        unpatch_reg_tables()
        indent = write_end_group(indent, 2, True)
    # ED prefix instructions
    elif i == 0xED:
        indent = write_begin_group(indent, i)
        for ii in range(0, 256) :
            write_op(indent, enc_ed_op(ii))
        indent = write_end_group(indent, 2, True)
    # CB prefix instructions
    elif i == 0xCB:
        indent = write_begin_group(indent, i, False)
        for ii in range(0, 256) :
            write_op(indent, enc_cb_op(ii, False, 'cc_cb'))
        indent = write_end_group(indent, 2, True)
    # non-prefixed instruction
    else:
        write_op(indent, enc_op(i, False, 'cc_op'))
write_end_group(indent, 1)
write_footer()
