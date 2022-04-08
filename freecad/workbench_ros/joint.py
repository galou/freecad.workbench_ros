from typing import Optional
import xml.etree.ElementTree as et

import FreeCAD as fc

from .utils import ICON_PATH
from .utils import add_property
from .utils import error
from .utils import get_placement
from .utils import valid_urdf_name
from .export_urdf import urdf_origin_from_placement


class Joint:
    """The Ros::Joint object."""

    type = 'Ros::Joint'

    # The names can be changed but not the order. Names can be added.
    type_enum = ['fixed', 'revolute', 'prismatic']

    def __init__(self, obj):
        obj.Proxy = self
        self.joint = obj
        self.init_properties(obj)

    def init_properties(self, obj):
        add_property(obj, 'App::PropertyString', '_Type', 'Internal',
                     'The type')._Type = Joint.type
        obj.setEditorMode('_Type', 3)  # Make read-only and hidden.

        add_property(obj, 'App::PropertyEnumeration', 'Type', 'Elements', 'The kinematical type of the joint')
        obj.Type = Joint.type_enum
        add_property(obj, 'App::PropertyLink', 'Parent', 'Elements', 'Parent link (from the ROS Workbench)')
        add_property(obj, 'App::PropertyLink', 'Child', 'Elements', 'Child link (from the ROS Workbench)')
        add_property(obj, 'App::PropertyPlacement', 'Origin', 'Elements', 'Joint origin relative to the parent link')
        add_property(obj, 'App::PropertyPlacement', 'Placement', 'Internal', 'The placement relative to the robot')
        obj.setPropertyStatus('Placement', 'Hidden')

    def onChanged(self, feature: fc.DocumentObjectGroup, prop: str) -> None:
        print(f'Joint::onChanged({feature.Name}, {prop})')

    def onDocumentRestored(self, obj):
        obj.Proxy = self
        self.joint = obj
        self.init_properties(obj)

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None

    def get_joint_placement(self):
        """Return the absolute joint placement."""
        return get_placement(self.joint.Parent.LinkedObject.Real[0]) * self.joint.Origin

    def export_urdf(self) -> et.ElementTree:
        joint_xml = et.fromstring('<joint/>')
        joint_xml.attrib['name'] = valid_urdf_name(self.name)
        joint_xml.attrib['type'] = self.joint.Type
        joint_xml.append(et.fromstring('<parent joint="{valid_urdf_name(self.parent.Label)}"/>'))
        joint_xml.append(et.fromstring('<child joint="{valid_urdf_name(self.child.Label)}"/>'))
        joint_xml.append(urdf_origin_from_placement(self.origin))
        joint_xml.append(et.fromstring('<axis xyz="0 0 1" />'))
        return joint_xml


class _ViewProviderJoint:
    """A view provider for the Joint container object """

    def __init__(self, vobj):
        vobj.Proxy = self

    def getIcon(self):
        # TODO: Solve why this doesn't work.
        # return 'ros_9dotslogo_color.svg'
        return str(ICON_PATH.joinpath('ros_9dotslogo_color.svg'))

    def attach(self, vobj):
        """Setup the scene sub-graph of the view provider."""
        pass

    def updateData(self, vobj: 'FreeCADGui.ViewProviderDocumentObject', prop):
        from .coin_utils import arrow_group
        from .coin_utils import transform_from_placement
        if (prop == 'Origin'):
            vobj.removeAllChildren()
            try:
                origin = vobj.Object.Origin
                # TODO: Include the robot placement.
                parent_placement = vobj.Object.Parent.Visual[0].Placement
            except (AttributeError, IndexError):
                return
            p0 = parent_placement.Base
            p1 = (parent_placement * origin).Base
            dp = p1 - p0
            p1_1m = p0 + dp * 1000 / dp.Length
            arrow = arrow_group([p0, p1_1m])
            vobj.RootNode.addChild(transform_from_placement(parent_placement))
            vobj.RootNode.addChild(arrow)

    def onChanged(self, vobj, prop):
        return

    def doubleClicked(self, vobj):
        gui_doc = vobj.Document
        if not gui_doc.getInEdit():
            gui_doc.setEdit(vobj.Object.Name)
        else:
            error('Task dialog already active')
        return True

    def setEdit(self, vobj, mode):
        import FreeCADGui as fcgui
        from .task_panel_joint import TaskPanelJoint
        task_panel = TaskPanelJoint(self.joint)
        fcgui.Control.showDialog(task_panel)
        return True

    def unsetEdit(self, vobj, mode):
        import FreeCADGui as fcgui
        fcgui.Control.closeDialog()
        return

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None


def makeJoint(name):
    """Add a Ros::Joint to the current document."""
    doc = fc.activeDocument()
    if doc is None:
        return
    obj = doc.addObject('Part::FeaturePython', name)
    Joint(obj)

    if fc.GuiUp:
        import FreeCADGui as fcgui

        _ViewProviderJoint(obj.ViewObject)

        # Make `obj` part of the selected `Ros::Robot`.
        sel = fcgui.Selection.getSelection()
        if sel:
            candidate = sel[0]
            if hasattr(candidate, '_Type') and candidate._Type == 'Ros::Robot':
                obj.adjustRelativeJoints(candidate)
                candidate.addObject(obj)

    return obj