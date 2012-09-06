import mathlink as _ml
import time as _time

_incoming_token = [_ml.RETURNPKT,
                   _ml.RETURNEXPRPKT,
                   _ml.DISPLAYPKT,
                   _ml.DISPLAYENDPKT,
                   _ml.RESUMEPKT,
                   _ml.RETURNTEXTPKT,
                   _ml.SUSPENDPKT,
                   _ml.MESSAGEPKT]

_id_to_mathematica = lambda x: str(x)

def _float_to_mathematica(x):
    return ("%e"%x).replace('e','*10^')

def _complex_to_mathematica(z):
    return 'Complex' + ('[%e,%e]'%(z.real,z.imag)).replace('e','*10^')

def _iter_to_mathematica(xs):
    s = 'List['
    for x in xs:
        s += _python_mathematica[type(x)](x)
        s += ','
    s = s[:-1]
    s+= ']'
    return s

def _str_to_mathematica(s):
    return '\"%s\"'%s

_python_mathematica = {bool:_id_to_mathematica,
                       type(None):_id_to_mathematica,
                       int:_id_to_mathematica,
                       float:_float_to_mathematica,
                       long:_id_to_mathematica,
                       complex:_complex_to_mathematica,
                       iter:_iter_to_mathematica,
                       list:_iter_to_mathematica,
                       set:_iter_to_mathematica,
                       xrange:_iter_to_mathematica,
                       str:_str_to_mathematica,
                       tuple:_iter_to_mathematica,
                       frozenset:_iter_to_mathematica}

def _mathematica_str_python(s):
    if s == 'Null':
        return None
    try:
        val = int(s)
    except ValueError:
        try:
            val = float(s)
        except ValueError:
            try:
                val = float(s.replace('*10^','e'))
            except ValueError:
                val = None
    # Some sort of Number, so return it NEED TO ADD COMPLEX and Rational
    if val is not None:
        return val
    val = {}
    s = s.replace(" ","").replace('{','List[').replace('}',']')
    open_brack = s.find("[")
    #Some String not a function Call, likely rational,complex,list or symbol
    if open_brack == -1:
        div = s.find('/')
        if div != -1:
            try:
                num = _mathematica_str_python(s[:div])
                den = _mathematica_str_python(s[div+1:])
                if num/den == float(num)/den:
                    return num/den
                else:
                    return float(num)/den
            except TypeError:
                val = s
        im = s.find('I')
        if im == -1:
            val = s
        else:
            plus = s.find('+')
            times = s.find('*I')
            if plus != -1:
                if times != -1:
                    try:
                        return complex(_mathematica_str_python(s[:plus]),
                                       _mathematica_str_python(s[plus+1:times]))
                    except TypeError:
                        val = s
                else:
                    try:
                        return complex(_mathematica_str_python(s[:plus]),1)
                    except TypeError:
                        val = s
            else:
                if times != -1:
                    try:
                        return complex(0,_mathematica_str_python(s[:times]))
                    except TypeError:
                        val = s
                else:
                    return complex(0,1)
        return val
    func = s[:open_brack]
    num_open_brack = 1
    val[func] = [] 
    last_comma = open_brack
    for i in range(open_brack+1,len(s)):
        if s[i] == ',' and num_open_brack == 1:
            val[func].append(_mathematica_str_python(s[last_comma+1:i]))
            last_comma = i
        elif s[i] == '[':
            num_open_brack += 1
        elif s[i] == ']':
            if num_open_brack > 1:
                num_open_brack -= 1
            elif num_open_brack == 1:
                val[func].append(_mathematica_str_python(s[last_comma+1:len(s)-1]))
            else:
                raise Exception("Unbalanced Brackets")
    if func == 'List':
        return val['List']
    elif func == 'Complex':
        return complex(val['Complex'][0],val['Complex'][1])
    elif func == 'Rational':
        return float(val['Rational'][0])/val['Rational'][1]
    else:
        return val


def _find_plot_strings(s):
    ps = []
    for g_func in ['Graphics[','Graphics3D[','Image[','Grid[']:
        while True:
            graph_start = s.find(g_func)
            if graph_start == -1:
                break
            num_brack = 1
            for i in range(graph_start+len(g_func),len(s)):
                if s[i] == '[':
                    num_brack += 1
                elif s[i] == ']':
                    if num_brack == 1:
                        ps.append(s[graph_start:i+1])
                        break
                    else:
                        num_brack -= 1
            s = s.replace(s[graph_start:i+1],'')
    return ps

class PythonicaException(Exception):
    pass

class Pythonica(object):

    def __init__(self,
                 name='math -mathlink',
                 mode='launch',
                 timeout=1,
                 debug=False,
                 plot_dir=None,
                 plot_size=None,
                 plot_format='png',
                 output_prompt=False,
                 input_prompt=False):
        self._env = _ml.env()
        self.kernel = self._env.open(name,mode=mode)
        self.kernel.connect()
        self.debug=debug
        self.plot_dir = plot_dir
        self.plot_num = 0
        self.last_python_result=None
        self.last_str_result=None
        self.plot_size = plot_size
        self.plot_format = plot_format
        self.output_prompt = output_prompt
        self.input_prompt = input_prompt
        self.last_error = None
        _time.sleep(timeout)
        if not self.kernel.ready():
            raise PythonicaException("Unable to Start Mathematica Kernel")
        else:
            packet = self.kernel.nextpacket()
            if self.debug:
                print _ml.packetdescriptiondictionary[packet]
            if packet == _ml.INPUTNAMEPKT:
                self.kernel.getstring()

    def eval(self,expression,make_plots=True,output_type='string',str_format='input'):
        self.last_python_result=None
        self.last_str_result=None
        self.last_error=None
        if str_format=='tex':
            expression = 'ToString[' + expression+',TeXForm]'
        elif str_format=='input':
            expression = 'ToString[' + expression + ',InputForm]'
        elif str_format=='plain':
            pass
        else:
            raise PythonicaException("String Format must be 'tex', 'input', or 'plain'")
        self.kernel.putfunction("EnterTextPacket",1)
        self.kernel.putstring(expression)
        self.__parse_packet()
        str_result = self.last_str_result
        if self.last_error is not None:
            raise PythonicaException(self.last_error.decode('string_escape'))
        if make_plots and self.plot_dir is not None:
            plot_exp = _find_plot_strings(str_result)
            for s in plot_exp:
                filename='\"%s/pythonica_plot_%i.%s\"'%(self.plot_dir,self.plot_num,self.plot_format)
                if self.plot_size is None:
                    self.eval('Export[%s,%s];'%(filename,s),make_plots=False,str_format='plain')
                else:
                    (w,h) = self.plot_size
                    self.eval('Export[%s,%s,ImageSize->{%i,%i}];'%(filename,s,w,h),make_plots=False,str_format='plain')
                self.plot_num += 1
        if str_format == 'plain':
            str_result = str_result.decode('string_escape')
        self.last_str_result = str_result
        if output_type == 'python':
            self.last_python_result = _mathematica_str_python(str_result)
            return self.last_python_result
        elif output_type == 'string':
            self.last_python_result = None
            return str_result
        else:
            raise PythonicaException("Output Type must be either 'python' or 'string'(default)")

    def push(self, name, value):
        convert_function = _python_mathematica.get(type(value),-1)
        if convert_function is -1:
            raise PythonicaException("Could not convert %s to Mathematica Object"%type(value))
        s = 'Set[%s,%s];'%(name,convert_function(value))
        self.eval(s,make_plots=False)

    def pull(self,name):
        res = self.eval(name,make_plots=False)
        return _mathematica_str_python(res)

    def __parse_packet(self):
        if self.debug:
            print("in __parse_packet")
        packet = self.kernel.nextpacket()
        if self.debug:
            print _ml.packetdescriptiondictionary[packet]
        if packet == _ml.INPUTNAMEPKT:
            if self.input_prompt:            
                print(self.kernel.getstring())
            else:
                self.kernel.getstring()
            return None 
        elif packet == _ml.OUTPUTNAMEPKT:
            if self.output_prompt:
                print(self.kernel.getstring())
            else:
                self.kernel.getstring()
            self.__parse_packet()
        elif packet == _ml.MESSAGEPKT:
            if self.last_error is None:
                self.last_error = self.kernel.getstring()
            else:
                self.last_error += "\t" + self.kernel.getstring()
            self.__parse_token(packet)
            self.__parse_packet()
        elif packet == _ml.TEXTPKT:
            self.last_error += self.kernel.getstring()
            self.__parse_packet()
        elif packet == _ml.SYNTAXPKT:
            self.kernel.getstring()
            self.__parse_packet()
        elif packet in _incoming_token:
            if self.debug:
                print("Going to Parse Token")
            self.last_str_result = self.__parse_token(packet).replace(r'\\\012','').replace(r'\012>   ','')
            self.__parse_packet()
        else:
            raise PythonicaException("Unknown Packet %s"%_ml.packetdescriptiondictionary[packet])


    def __parse_token(self,packet):
        if self.debug:
            print("In Parse Token")
        try:
            token = self.kernel.getnext()
            if self.debug:
                print _ml.tokendictionary[token]
        except _ml.error, e:
            raise PythonicaException("Got Error Token: %s"%e)
        if token == _ml.MLTKSTR:
            return self.kernel.getstring()
        else:
            raise PythonicaException("Unknown Token %i",token)

    def __del__(self):
        self.kernel.close()



import os as _os

if __name__ =="__main__":
    m = Pythonica(plot_dir=_os.getcwd(),debug=False)
    try:
        m.eval("asl]]];dfkja")
    except PythonicaException,e:
        print(e)
    print m.eval('Series[f[x],{x,0,6}]')
    print m.eval('Series[f[x],{x,0,6}]',str_format='tex')
    test = m.eval('Series[f[x],{x,0,6}]')
    print m.eval(test)
    
    inputs = ['5',
              'X=5/2',
              'X',
              '3+5I',
              '{1,2,3,4}',
              'D[Log[x],x]',
              'GraphPlot[{1 -> 2, 1 -> 4, 2 -> 4, 3 -> 4, 3 -> 2, 3 ->5,5->1}, VertexLabeling -> True]', 
              '{Plot[Sin[x],{x,0,10}],Plot[Cos[x],{x,0,10}]}',
              'Plot3D[Sin[x y], {x, 0, 3}, {y, 0, 3}, ColorFunction->"Rainbow", Mesh -> None]',
              'Unevaluated[Image[CellularAutomaton[30, {{1}, 0},40],\"Bit\"]]',
              'Grid[{{a,b,c},{x,y^2,z^3}},Frame->All]']
    print m.eval(inputs[5])
    print m.eval(inputs[5],str_format='tex')

    m.input_prompt=True
    m.output_prompt=True

    print m.eval(inputs[5])
    print m.eval(inputs[5],str_format='tex')

    m.input_prompt=False
    m.output_prompt=False
    
    i = 1
    for inp in inputs:
        print('In[%i]= '%i + inp)
        if i>6:
            m.eval(inp)
        else:
            print m.eval(inp)
        i+=1
    
    m.plot_size=(600,400)
    m.eval(inputs[-3])
    m.plot_size=(800,600)
    m.eval(inputs[-3])
    m.plot_size=None

    m.plot_format='jpeg'
    m.eval(inputs[-4])
    m.plot_format='svg'
    m.eval(inputs[-4])
    m.plot_format='bmp'
    m.eval(inputs[-4])
    
    m.push('x',5)
    m.push('l',4L)
    m.push('y',.5)
    m.push('z',complex(3,4))
    m.push('t',True)
    m.push('f',False)
    m.push('nan',None)
    m.push('r',range(5))
    m.push('L',[1,2,3])
    m.push('s',set([1,2,3]))
    m.push('xr',xrange(4))
    m.push('st','hello')
    m.push('fs',frozenset([1,2,3]))
    m.push('ll',[1,2,'hello',[2,2,3],complex(3,4)])

    print m.eval('x')
    print m.eval('l')
    print m.eval('y')
    print m.eval('z')
    print m.eval('t')
    print m.eval('f')
    print m.eval('nan')
    print m.eval('r')
    print m.eval('L')
    print m.eval('s')
    print m.eval('xr')
    print m.eval('st')
    print m.eval('fs')
    print m.eval('ll')

    print m.pull('x')
    print m.pull('l')
    print m.pull('y')
    print m.pull('z')
    print m.pull('t')
    print m.pull('f')
    print m.pull('nan')
    print m.pull('r')
    print m.pull('L')
    print m.pull('s')
    print m.pull('xr')
    print m.pull('st')
    print m.pull('fs')
    print m.pull('ll')
