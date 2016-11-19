# BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# END GPL LICENSE BLOCK #####

import os
import sys
import ast
import traceback

import bpy
from bpy.props import StringProperty, IntVectorProperty, FloatVectorProperty

from sverchok.utils.sv_panels_tools import sv_get_local_path
from sverchok.node_tree import SverchCustomTreeNode
from sverchok.data_structure import dataCorrect, updateNode, replace_socket

TRIPPLE_QUOTES = '"""'
UNPARSABLE = None, None, None, None
FAIL_COLOR = (0.8, 0.1, 0.1)
READY_COLOR = (0, 0.8, 0.95)

sv_path = os.path.dirname(sv_get_local_path()[0])
snlite_template_path = os.path.join(sv_path, 'node_scripts', 'SNLite_templates')

defaults = list(range(32))
sock_dict = {
    'v': 'VerticesSocket', 's': 'StringsSocket', 'm': 'MatrixSocket', 'o': 'SvObjectSocket'
}


def processed(str_in):
    _, b = str_in.split('=')
    return ast.literal_eval(b)


def parse_socket_line(line):
    lsp = line.strip().split()
    if not len(lsp) in {3, 5}:
        print(line, 'is malformed')
        return UNPARSABLE
    else:
        socket_type = sock_dict.get(lsp[2])
        socket_name = lsp[1]
        if not socket_type:
            return UNPARSABLE
        elif len(lsp) == 3:
            return socket_type, socket_name, None, None
        else:
            default = processed(lsp[3])
            nested = processed(lsp[4])
            return socket_type, socket_name, default, nested


def parse_sockets(node):
    socket_info = {'inputs': [], 'outputs': []}
    quotes = 0
    for line in node.script_str.split('\n'):
        L = line.strip()
        if L.startswith(TRIPPLE_QUOTES):
            quotes += 1
            if quotes == 2:
                break
        elif L.startswith('in ') or L.startswith('out '):
            socket_dir = L.split(' ')[0] + 'puts'
            socket_info[socket_dir].append(parse_socket_line(L))
        elif L.startswith('draw '):
            drawfunc_line = L.split(' ')
            if len(drawfunc_line) == 2:
                socket_info['drawfunc_name'] = drawfunc_line[1]

    return socket_info


def are_matched(sock_, socket_description):
    return (sock_.bl_idname, sock_.name) == socket_description[:2]


class SvScriptNodeLitePyMenu(bpy.types.Menu):
    bl_label = "SNLite templates"
    bl_idname = "SvScriptNodeLitePyMenu"

    def draw(self, context):
        # load simply as Text File into a textblok
        # self.path_menu([snlite_template_path], "text.open", {"internal": True})
        
        # load straight into current SNlite
        self.path_menu([snlite_template_path], "node.scriptlite_import")


class SvScriptNodeLiteCallBack(bpy.types.Operator):

    bl_idname = "node.scriptlite_ui_callback"
    bl_label = "SNLite callback"
    fn_name = bpy.props.StringProperty(default='')

    def execute(self, context):
        getattr(context.node, self.fn_name)()
        return {'FINISHED'}


class SvScriptNodeLiteTextImport(bpy.types.Operator):

    bl_idname = "node.scriptlite_import"
    bl_label = "SNLite load"
    filepath = bpy.props.StringProperty()

    def execute(self, context):
        txt = bpy.data.texts.load(self.filepath)
        context.node.script_name = os.path.basename(txt.name)
        context.node.load()
        return {'FINISHED'}


class SvScriptNodeLite(bpy.types.Node, SverchCustomTreeNode):

    ''' Script node Lite'''
    bl_idname = 'SvScriptNodeLite'
    bl_label = 'Scripted Node Lite'
    bl_icon = 'SCRIPTPLUGINS'

    script_name = StringProperty()
    script_str = StringProperty()
    node_dict = {}

    int_list = IntVectorProperty(
        name='int_list', description="Integer list",
        default=defaults, size=32, update=updateNode)

    float_list = FloatVectorProperty(
        name='float_list', description="Float list",
        default=defaults, size=32, update=updateNode)


    def draw_label(self):
        if self.script_name:
            return 'SN: ' + self.script_name
        else:
            return self.bl_label


    def draw_buttons(self, context):
        ref = self.node_dict.get(hash(self))
        if ref:
            _info = ref['sockets']
            draw = _info.get('drawfunc')


    def draw_buttons_ext(self, context, layout):
        layout.menu(SvScriptNodeLitePyMenu.bl_idname)


    def add_or_update_sockets(self, k, v):
        '''
        'sockets' are either 'self.inputs' or 'self.outputs'
        '''
        sockets = getattr(self, k)

        for idx, (socket_description) in enumerate(v):
            if socket_description is UNPARSABLE: 
                print(socket_description, idx, 'was unparsable')
                return

            if len(sockets) > 0 and idx in set(range(len(sockets))):
                if not are_matched(sockets[idx], socket_description):
                    replace_socket(sockets[idx], *socket_description[:2])
            else:
                sockets.new(*socket_description[:2])

        return True


    def add_props_to_sockets(self, socket_info):

        self.id_data.freeze(hard=True)
        try:
            for idx, (socket_description) in enumerate(socket_info['inputs']):
                dval = socket_description[2]
                print(idx, socket_description)

                s = self.inputs[idx]

                if isinstance(dval, float):
                    s.prop_type = "float_list"
                    s.prop_index = idx
                    self.float_list[idx] = dval

                elif isinstance(dval, int):
                    s.prop_type = "int_list"
                    s.prop_index = idx
                    self.int_list[idx] = dval
        except:
            print('some failure in the add_props_to_sockets function. ouch.')

        self.id_data.unfreeze(hard=True)

    
    def flush_excess_sockets(self, k, v):
        sockets = getattr(self, k)
        if len(sockets) > len(v):
            num_to_remove = (len(sockets) - len(v))
            for i in range(num_to_remove):
                sockets.remove(sockets[-1])


    def update_sockets(self):
        socket_info = parse_sockets(self)
        if not socket_info['inputs']:
            return

        for k, v in socket_info.items():
            if not (k in {'inputs', 'outputs'}): continue

            if not self.add_or_update_sockets(k, v):
                print('failed to load sockets for ', k)
                return

            self.flush_excess_sockets(k, v)

        self.add_props_to_sockets(socket_info)
        self.node_dict[hash(self)] = {}
        self.node_dict[hash(self)]['sockets'] = socket_info

        return True


    def sv_init(self, context):
        self.use_custom_color = False


    def load(self):
        if not self.script_name:
            return
        self.script_str = bpy.data.texts.get(self.script_name).as_string()

        if self.update_sockets():
            self.process()


    def nuke_me(self):
        self.script_str = ''
        self.script_name = ''
        self.node_dict[hash(self)] = {}
        for socket_set in [self.inputs, self.outputs]:
            socket_set.clear()        

    def copy(self, node):
        self.node_dict[hash(self)] = {}
        self.load()

    def process(self):
        if not all([self.script_name, self.script_str]):
            return
        self.process_script()


    def make_new_locals(self):

        # make .blend reload event work, without this the self.node_dict is empty.
        if not self.node_dict:
            # self.load()
            self.update_sockets()

        # make inputs local, do function with inputs, return outputs if present
        socket_info = self.node_dict[hash(self)]['sockets']
        local_dict = {}
        for idx, s in enumerate(self.inputs):
            sock_desc = socket_info['inputs'][idx]
            
            if s.is_linked:
                val = s.sv_get(default=[[]])
                if sock_desc[3]:
                    val = {0: val, 1: val[0], 2: val[0][0]}.get(sock_desc[3])
            else:
                val = sock_desc[2]
                if isinstance(val, (int, float)):
                    # extra pussyfooting for the load sequence.
                    t = s.sv_get(default=[[val]])
                    if t and t[0] and t[0][0]:
                        val = t[0][0]

            local_dict[s.name] = val

        return local_dict


    def process_script(self):
        locals().update(self.make_new_locals())

        try:
            exec(self.script_str, locals(), locals())
            for idx, _socket in enumerate(self.outputs):
                vals = locals()[_socket.name]
                self.outputs[idx].sv_set(vals)

            socket_info = self.node_dict[hash(self)]['sockets']
            __fnamex = socket_info.get('drawfunc_name')
            if __fnamex:
                socket_info['drawfunc'] = locals()[__fnamex]

            self.use_custom_color = True
            self.color = READY_COLOR

        except Exception as err:
            # this does not find the line in the exec string ( I KNOW )
            sys.stderr.write('ERROR: %s\n' % str(err))
            print(sys.exc_info()[-1].tb_frame.f_code)
            print('Error on line {}'.format(sys.exc_info()[-1].tb_lineno))
            print('failed execution')
            self.use_custom_color = True
            self.color = FAIL_COLOR


    def custom_draw(self, context, layout):
        tk = self.node_dict.get(hash(self))
        if not tk or not tk.get('sockets'):
            return

        socket_info = tk['sockets']
        if socket_info:
            f = socket_info.get('drawfunc')
            if f:
                f(self, context, layout)


    def draw_buttons(self, context, layout):
        sn_callback = 'node.scriptlite_ui_callback'

        col = layout.column(align=True)
        row = col.row()

        if not self.script_str:
            row.prop_search(self, 'script_name', bpy.data, 'texts', text='', icon='TEXT')
            row.operator(sn_callback, text='', icon='PLUGIN').fn_name = 'load'
        else:
            row.operator(sn_callback, text='Reload').fn_name = 'load'
            row.operator(sn_callback, text='Clear').fn_name = 'nuke_me'

        self.custom_draw(context, layout)


classes = [SvScriptNodeLiteTextImport, SvScriptNodeLitePyMenu, SvScriptNodeLiteCallBack, SvScriptNodeLite]


def register():
    [bpy.utils.register_class(name) for name in classes]


def unregister():
    [bpy.utils.unregister_class(name) for name in classes]