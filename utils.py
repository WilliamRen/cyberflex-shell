import pycsc, string, binascii, sys

_myprintable = " " + string.letters + string.digits + string.punctuation
def hexdump(data, indent = 0, short = False):
    r"""Generates a nice hexdump of data and returns it. Consecutive lines will 
    be indented with indent spaces. When short is true, will instead generate 
    hexdump without adresses and on one line.
    
    Examples: 
    hexdump('\x00\x41') -> \
    '0000:  00 41                                             .A              '
    hexdump('\x00\x41', short=True) -> '00 41 (.A)'"""
    
    def hexable(data):
        return " ".join([binascii.b2a_hex(a) for a in data])
    
    def printable(data):
        return "".join([e in _myprintable and e or "." for e in data])
    
    if short:
        return "%s (%s)" % (hexable(data), printable(data))
    
    result = ""
    (head, tail) = (data[:16], data[16:])
    pos = 0
    while len(head) > 0:
        if pos > 0:
            result = result + "\n%s" % (' ' * indent)
        result = result + "%04x:  %-48s  %-16s" % (pos, hexable(head), printable(head))
        pos = pos + len(head)
        (head, tail) = (tail[:16], tail[16:])
    return result

LIFE_CYCLES = {0x01: "Load file = loaded",
    0x03: "Applet instance / security domain = Installed",
    0x07: "Card manager = Initialized; Applet instance / security domain = Selectable",
    0x0F: "Card manager = Secured; Applet instance / security domain = Personalized",
    0x7F: "Card manager = Locked; Applet instance / security domain = Blocked",
    0xFF: "Applet instance = Locked"}

def parse_status(data):
    """Parses the Response APDU of a GetStatus command."""
    def parse_segment(segment):
        def parse_privileges(privileges):
            if privileges == 0x0:
                return "N/A"
            else:
                privs = []
                if privileges & (1<<7):
                    privs.append("security domain")
                if privileges & (1<<6):
                    privs.append("DAP DES verification")
                if privileges & (1<<5):
                    privs.append("delegated management")
                if privileges & (1<<4):
                    privs.append("card locking")
                if privileges & (1<<3):
                    privs.append("card termination")
                if privileges & (1<<2):
                    privs.append("default selected")
                if privileges & (1<<1):
                    privs.append("global PIN modification")
                if privileges & (1<<0):
                    privs.append("mandated DAP verification")
                return ", ".join(privs)
        
        lgth = ord(segment[0])
        aid = segment[1:1+lgth]
        lifecycle = ord(segment[1+lgth])
        privileges = ord(segment[1+lgth+1])
        
        print "aid length:       %i (%x)" % (lgth, lgth)
        print "aid:              %s" % hexdump(aid, indent = 18, short=True)
        print "life cycle state: %x (%s)" % (lifecycle, LIFE_CYCLES.get(lifecycle, "unknown or invalid state"))
        print "privileges:       %x (%s)\n" % (privileges, parse_privileges(privileges))

    pos = 0
    while pos < len(data):
        lgth = ord(data[pos])+3
        segment = data[pos:pos+lgth]
        parse_segment(segment)
        pos = pos + lgth

def _unformat_hexdump(dump):
    hexdump = " ".join([line[7:54] for line in dump.splitlines()])
    return binascii.a2b_hex("".join([e != " " and e or "" for e in hexdump]))

class APDU:
    "Base class for an APDU"
    
    def __init__(self, *args, **kwargs):
        """Creates a new APDU instance. Can be given positional parameters which 
        must be sequences of either strings (or strings themselves) or integers
        specifying byte values that will be concatenated in order. Alternatively
        you may give exactly one positional argument that is an APDU instance.
        After all the positional arguments have been concatenated they must
        form a valid APDU!
        
        The keyword arguments can then be used to override those values.
        Keywords recognized are: 
            C_APDU: cla, ins, p1, p2, lc, le, data
            R_APDU: sw, sw1, sw2, data
        """
        
        initbuff = list()
        
        if len(args) == 1 and isinstance(args[0], self.__class__):
            self.parse( args[0].render() )
        else:
            for arg in args:
                if type(arg) == str:
                    initbuff.extend(arg)
                elif hasattr(arg, "__iter__"):
                    for elem in arg:
                        if hasattr(elem, "__iter__"):
                            initbuff.extend(elem)
                        else:
                            initbuff.append(elem)
                else:
                    initbuff.append(arg)
            
            for (index, value) in enumerate(initbuff):
                t = type(value)
                if t == str:
                    initbuff[i] = ord(value)
                elif t != int:
                    raise TypeError, "APDU must consist of ints or one-byte strings, not %s (index %s)" % (t, index)
            
            self.parse( initbuff )
        
        for (name, value) in kwargs.items():
            print "setting %r=%r" % (name, value)
            setattr(self, name, value)
            print "is now %r" % getattr(self, name)
        print "cla=%r" % self.cla
    
    def _getdata(self):
        return self._data
    def _setdata(self, value): 
        if isinstance(value, str):
            self._data = [ord(e) for e in value]
        elif isinstance(value, list):
            self._data = [int(e) for e in value]
        else:
            raise ValueError, "'data' attribute can only be a str or a list of int, not %s" % type(value)
    def _deldata(self):
        del self._data; self.data = ""
    
    data = property(_getdata, _setdata, None,
        "The data contents of this APDU")
    
    def _setbyte(self, name, value):
        print "setbyte(%r, %r)" % (name, value)
        if isinstance(value, int):
            setattr(self, "_"+name, value)
        elif isinstance(value, str):
            setattr(self, "_"+name, ord(value))
        else:
            raise ValueError, "'%s' attribute can only be a byte, that is: int or str, not %s" % (namelower, type(value))
    
def _make_byte_properties(obj, props):
    "Generates properties for all names in props and their lowercase equivalents"
    ## This is because I was too lazy to type it all out. Ignore it if you don't know what it's good for
    for v in props:
        setattr(obj, v, 
            property(lambda self: getattr(self, "_"+v, 0),
                lambda self: self._setbyte(v, value), None,
                "The %s attribute of the APDU" % v)
        )
        setattr(obj, v.lower(), 
            property(lambda self: getattr(self, "_"+v, 0),
                lambda self: self._setbyte(v, value), None,
                "The %s attribute of the APDU" % v)
        )

class C_APDU(APDU):
    "Class for a command APDU"
    
    def parse(self, apdu):
        "Parse a full command APDU and assign the values to our object, overwriting whatever there was."
        print "parse(%r)" % apdu

_make_byte_properties(C_APDU, ("CLA", "INS", "P1", "P2", "Lc", "Le") )

class R_APDU(APDU):
    "Class for a response APDU"
    
    def _getsw(self):        return chr(self._sw1) + chr(self._sw2)
    def _setsw(self, value):
        if len(value) != 2:
            raise ValueError, "SW must be exactly two bytes"
        self.sw1 = value[0]
        self.sw2 = value[1]
    
    SW = property(_getsw, _setsw, None,
        "The Status Word of this response APDU")
    sw = SW
    
    def parse(self, apdu):
        "Parse a full response APDU and assign the values to our object, overwriting whatever there was."
        self.sw = apdu[-2:]
        self.data = apdu[:-2]

_make_byte_properties(C_APDU, ("SW1", "SW2") )

class TPDU:
    "Base class for TPDUs"
    
    def __init__(self, apdu):
        self.apdu = apdu
    
class TPDU_T0(TPDU):
    "Class for a T=0 TPDU"
    protocol = 0

class TPDU_T1(TPDU):
    "Class for T=1 TPDU"
    protocol = 1

class APDU_old:
    """Class for an APDU.."""
    OFFSET_CLA = 0
    OFFSET_INS = 1
    OFFSET_P1 = 2
    OFFSET_P2 = 3
    OFFSET_LE = 4
    OFFSET_LC = 4
    
    def __init__(self, *args, **kwargs):
        """Creates a new APDU instance. Can be given positional parameters which 
        must be sequences of either strings (or strings themselves) or integers
        specifying byte values that will be concatenated in order. Alternatively
        you may give exactly one positional argument that is an APDU instance.
        After all the positional arguments have been concatenated they must
        form a valid APDU!
        
        The keyword arguments can then be used to override those values.
        Keywords recognized are: cla, ins, p1, p2, lc, le, content.
        
        If protocol is set to 0 then the APDU will be parsed as a T=0 APDU."""
        
        initbuff = list()
        
        if len(args) == 1 and isinstance(args[0], APDU):
            initbuff.extend(args[0].get_string())
        else:
            for arg in args:
                if type(arg) == str:
                    initbuff.extend(arg)
                elif hasattr(arg, "__iter__"):
                    for elem in arg:
                        if hasattr(elem, "__iter__"):
                            initbuff.extend(elem)
                        else:
                            initbuff.append(elem)
                else:
                    initbuff.append(arg)
        
        for i in range(len(initbuff)):
            t = type(initbuff[i])
            if t == str:
                initbuff[i] = ord(initbuff[i])
            elif t != int:
                raise TypeError, "APDU must consist of ints or one-byte strings, not %s (index %s)" % (t, i)
        
        if len(initbuff) < 4:
            initbuff.extend( [0] * (4-len(initbuff)) )
        
        self.__dict__.update( {
            "cla": initbuff[self.OFFSET_CLA],
            "ins": initbuff[self.OFFSET_INS],
            "p1": initbuff[self.OFFSET_P1],
            "p2": initbuff[self.OFFSET_P2]
        } )
        
        lc_was_set = False
        
        if kwargs.get("protocol", None) == 0:
            if len(initbuff) == 4: ## ISO case 1
                self.le = 0
                self.lc = 0
                self.content = list()
            elif len(initbuff) == 5: ## ISO case 2
                self.le = initbuff[self.OFFSET_LE]
                self.lc = 0
                self.content = list()
            elif len(initbuff) > 5:
                self.lc = initbuff[self.OFFSET_LC]
                lc_was_set = True
                if len(initbuff) == 5 + self.lc: ## ISO case 3
                    self.le = 0
                    self.content = initbuff[5:5+self.lc]
                elif len(initbuff) == 5 + self.lc + 1: ## ISO case 4
                    self.le = initbuff[-1]
                    self.content = initbuff[5:5+self.lc]
                else:
                    raise ValueError, "Invalid APDU, length(%i) != 4 + 1 + lc(%i) + 1" % (len(initbuff), self.lc)
            else:
                raise ValueError, "Invalid APDU, impossible"
        else:
            self.le = 0
            self.lc = len(initbuff)-4
            self.content = initbuff[4:]
        
        for (kw_orig, arg) in kwargs.items():
            kw = kw_orig.lower()
            if kw == "cla":
                self.cla = arg
            elif kw == "ins":
                self.ins = arg
            elif kw == "p1":
                self.p1 = arg
            elif kw == "p2":
                self.p2 = arg
            elif kw == "lc":
                self.lc = arg
                lc_was_set = True
            elif kw == "le":
                self.le = arg
            elif kw == "content":
                self.content = arg
            else:
                raise TypeError, "Got an unexpected keyword argument '%s'" % kw_orig
        
        if not lc_was_set:
            self.lc = len(self.content)
    
    def __str__(self):
        result = len(self.content) != self.lc and "Invalid " or ""
        result = result + "APDU(CLA=0x%x, INS=0x%x, P1=0x%x, P2=0x%x" % (
            self.cla, self.ins, self.p1, self.p2)
        if self.lc == 0 and self.le == 0: ## ISO case 1
            result = result + ")"
        elif self.lc == 0 and self.le > 0: ## ISO case 2:
            result = result + ", LE=0x%x)" % self.le
        elif self.lc > 0 and self.le == 0: ## ISO case 3
            result = result + ", LC=0x%x)" % self.lc
        elif self.lc > 0 and self.le > 0: ## ISO case 4:
            result = result + ", LC=0x%x, LE=0x%x)" % (
                self.lc, self.le
            )
        else:
            raise ValueError, "Impossible error. Call the X files."
        
        if len(self.content) > 0:
            result = result + " with %i(0x%x) bytes of contents" % (
                len(self.content), len(self.content) 
            )
        
        return result + ":\n" + hexdump(self.get_string())
    
    def __repr__(self):
        result = "APDU(CLA=0x%x, INS=0x%x, P1=0x%x, P2=0x%x" % (
            self.cla, self.ins, self.p1, self.p2)
        if self.lc == 0 and self.le == 0: ## ISO case 1
            pass
        elif self.lc == 0 and self.le > 0: ## ISO case 2:
            result = result + ", LE=0x%x" % self.le
        elif self.lc > 0 and self.le == 0: ## ISO case 3
            result = result + ", LC=0x%x" % self.lc
        elif self.lc > 0 and self.le > 0: ## ISO case 4:
            result = result + ", LC=0x%x, LE=0x%x" % (
                self.lc, self.le
            )
        else:
            raise ValueError, "Impossible error. Call the X files."
        
        if len(self.content) > 0:
            result = result + ", content=%r)" % self.content
        else:
            result = result + ")"
        
        return result
    
    _bytevars = ("cla", "ins", "p1", "p2", "lc", "le")
    _bytelistvars = ("content",)
    def __setattr__(self, name, value):
        namelower = name.lower()
        if namelower in self._bytevars:
            if isinstance(value, int):
                self.__dict__[namelower] = value
            elif isinstance(value, str):
                self.__dict__[namelower] = ord(value)
            else:
                raise ValueError, "'%s' attribute can only be a byte, that is: int or str, not %s" % (namelower, type(value))
        elif namelower in self._bytelistvars:
            if isinstance(value, str):
                self.__dict__[namelower] = [ord(e) for e in value]
            elif isinstance(value, list):
                self.__dict__[namelower] = [int(e) for e in value]
            else:
                raise ValueError, "'%s' attribute can only be a byte list, that is: list of int or str, not %s" (namelower, type(value))
        else:
            self.__dict__[name] = value
    
    def get_string(self, protocol=None):
        """Return the contents of this APDU as a binary string.
        If protocol is set to 0 then the APDU will be rendered as a T=0 APDU."""
        contents = [self.cla, self.ins, self.p1, self.p2]
        if protocol == 0:
            if self.lc > 0:
                contents.extend( [self.lc] + self.content)
            if self.le > 0:
                contents.append( self.le )
        else:
            contents.extend( self.content )
        return "".join([i is not None and chr(i) or "?" for i in contents])
    
    def append_content(self, string):
        self.content = self.content + string
        self.lc = len(self.content)
    
if __name__ == "__main__":
    response = """
0000:  07 A0 00 00 00 03 00 00 07 00 07 A0 00 00 00 62  ...............b
0010:  00 01 01 00 07 A0 00 00 00 62 01 01 01 00 07 A0  .........b......
0020:  00 00 00 62 01 02 01 00 07 A0 00 00 00 62 02 01  ...b.........b..
0030:  01 00 07 A0 00 00 00 03 00 00 01 00 0E A0 00 00  ................
0040:  00 30 00 00 90 07 81 32 10 00 00 01 00 0E A0 00  .0.....2........
0050:  00 00 30 00 00 90 07 81 42 10 00 00 01 00 0E A0  ..0.....B.......
0060:  00 00 00 30 00 00 90 07 81 41 10 00 00 07 00 0E  ...0.....A......
0070:  A0 00 00 00 30 00 00 90 07 81 12 10 00 00 01 00  ....0...........
0080:  09 53 4C 42 43 52 59 50 54 4F 07 00 90 00        .SLBCRYPTO....  
""" # 64kv1 vorher
    response = """
0000:  07 A0 00 00 00 03 00 00 0F 00 07 A0 00 00 00 62  ...............b
0010:  00 01 01 00 07 A0 00 00 00 62 01 01 01 00 07 A0  .........b......
0020:  00 00 00 62 01 02 01 00 07 A0 00 00 00 62 02 01  ...b.........b..
0030:  01 00 07 A0 00 00 00 03 00 00 01 00 08 A0 00 00  ................
0040:  00 30 00 CA 10 01 00 0E A0 00 00 00 30 00 00 90  .0..........0...
0050:  07 81 32 10 00 00 01 00 0E A0 00 00 00 30 00 00  ..2..........0..
0060:  90 07 81 42 10 00 00 01 00 0E A0 00 00 00 30 00  ...B..........0.
0070:  00 90 07 81 41 10 00 00 07 00 0E A0 00 00 00 30  ....A..........0
0080:  00 00 90 07 81 12 10 00 00 01 00 09 53 4C 42 43  ............SLBC
0090:  52 59 50 54 4F 07 00 90 00                       RYPTO....       
""" # komische Karte
    response = """
0000:  07 A0 00 00 00 03 00 00 07 00 07 A0 00 00 00 62  ...............b
0010:  00 01 01 00 07 A0 00 00 00 62 01 01 01 00 07 A0  .........b......
0020:  00 00 00 62 01 02 01 00 07 A0 00 00 00 62 02 01  ...b.........b..
0030:  01 00 07 A0 00 00 00 03 00 00 01 00 0E A0 00 00  ................
0040:  00 30 00 00 90 07 81 32 10 00 00 01 00 0E A0 00  .0.....2........
0050:  00 00 30 00 00 90 07 81 42 10 00 00 01 00 0E A0  ..0.....B.......
0060:  00 00 00 30 00 00 90 07 81 41 10 00 00 07 00 0E  ...0.....A......
0070:  A0 00 00 00 30 00 00 90 07 81 12 10 00 00 01 00  ....0...........
0080:  09 53 4C 42 43 52 59 50 54 4F 07 00 05 A0 00 00  .SLBCRYPTO......
0090:  00 01 01 00 90 00                                ......          
""" # 64kv1 nachher
    response = """
0000:  07 A0 00 00 00 03 00 00 07 00 07 A0 00 00 00 62  ...............b
0010:  00 01 01 00 07 A0 00 00 00 62 01 01 01 00 07 A0  .........b......
0020:  00 00 00 62 01 02 01 00 07 A0 00 00 00 62 02 01  ...b.........b..
0030:  01 00 07 A0 00 00 00 03 00 00 01 00 0E A0 00 00  ................
0040:  00 30 00 00 90 07 81 32 10 00 00 01 00 0E A0 00  .0.....2........
0050:  00 00 30 00 00 90 07 81 42 10 00 00 01 00 0E A0  ..0.....B.......
0060:  00 00 00 30 00 00 90 07 81 41 10 00 00 07 00 0E  ...0.....A......
0070:  A0 00 00 00 30 00 00 90 07 81 12 10 00 00 01 00  ....0...........
0080:  09 53 4C 42 43 52 59 50 54 4F 07 00 05 A0 00 00  .SLBCRYPTO......
0090:  00 01 01 00 06 A0 00 00 00 01 01 07 02 90 00     ............... 
""" # 64k1 nach setup
    #response = sys.stdin.read()
    #parse_status(_unformat_hexdump(response)[:-2])
    
    print C_APDU((1,2,3), cla=0x23, data="hallo")
    print C_APDU(1,2,3,4,2,4,6)
    
    c = C_APDU()
    c.cla = 'a'
    print "\n",c.cla
    
