from typing import Iterable,List,Optional

import FreeCAD as fc

from .utils import ICON_PATH
from .utils import add_property
from .utils import error
from .utils import get_links

# Typing hint aliases
DO = fc.DocumentObject


def _existing_link(link: DO, o: DO) -> Optional[DO]:
    """Return the link to o if it exists in link.Group.

    Parameters
    ----------
    - link: a FreeCAD object proxied to Link.

    """
    for linked_lod in link.Group:
        if linked_lod.LinkedObject is o:
            return linked_lod


def _add_links_lod(link: DO, objects: List[DO], lod: str) -> List[DO]:
    """Add a level of detail to a Ros::Link.

    Return the full list of linked objects (existing + created).

    Parameters
    ----------
    - link: a FreeCAD object of type Ros::Link.
    - objects: the list of objects to potentially add.
    - lod: string describing the level of details.

    """
    doc = link.Document
    old_and_new_objects: List[DO] = []
    for o in objects:
        link_to_o = _existing_link(link, o)
        if link_to_o is not None:
            # print(f' {o.Name} is already linked')
            old_and_new_objects.append(link_to_o)
            continue
        name = f'{lod}_{link.Name}000'
        lod_link = doc.addObject('App::Link', name)
        lod_link.Label = name
        # TODO: set lod_link.LinkPlacement:
        # - Get the path of o in the assembly in the form Assembly.object0
        # - Get the placement of o with Assembly.getSubObject(path, retType=3),
        #   cf. https://forum.freecadweb.org/viewtopic.php?f=22&t=65851&p=572213#p569083
        # print(f'Adding link {lod_link.Name} to {o.Name} into {link.Name}')
        if len(o.Parents) != 1:
            warn(f'Wrong object type. {o.Name}.Parents has more than one entry')
        link_placement = fc.Placement()
        if o.Parents:
            parent, subname = o.Parents[0]
            link_placement = parent.getSubObject(subname, retType=3)
        lod_link.LinkPlacement = link_placement
        lod_link.setLink(o)
        lod_link.adjustRelativeLinks(link)
        link.addObject(lod_link)
        old_and_new_objects.append(lod_link)
        print(f'Appending {lod_link.Name}')
    return old_and_new_objects


class Robot:
    """The Robot group."""
    def __init__(self, obj):
        obj.Proxy = self
        self.robot = obj
        self.type = 'Ros::Robot'
        self.previous_link_count = 0

        self.init_properties(obj)

    def init_properties(self, obj):
        add_property(obj, 'App::PropertyString', 'Type', 'Internal',
                    'The type').Type = self.type
        obj.setEditorMode('Type', 3)  # Make read-only and hidden.
        # obj.setPropertyStatus('Type', 'Hidden')?
        obj.setEditorMode('Group', 1)  # Read-only, managed in self.reset_group().

        add_property(obj, 'App::PropertyLink', 'Assembly', 'Components',
                    'The part object this robot is built upon')
        add_property(obj, 'App::PropertyBool', 'ShowReal', 'Components',
                    'Whether to show the real parts').ShowReal = True
        add_property(obj, 'App::PropertyBool', 'ShowVisual', 'Components',
                    'Whether to show the parts for URDF visual').ShowVisual = False
        add_property(obj, 'App::PropertyBool', 'ShowCollision', 'Components',
                    'Whether to show the parts for URDF collision').ShowCollision = False

        add_property(obj, 'App::PropertyPath', 'OutputPath', 'Export',
                    'The path to the ROS package to export files to')

    def execute(self, obj):
        self.reset_group()

    def onBeforeChange(self, feature: DO, prop: str) -> None:
        print(f'Robot::onBeforeChange({feature.Name}, {prop})')
        if not hasattr(self, 'robot'):
            # Implementation note: happens but how is it possible?
            print('self has no "robot"') # DEBUG
            return
        # if prop in ['Group', 'ShowReal', 'ShowVisual', 'ShowCollision']:
        #     self.reset_group()

        try:
            self.previous_show_real = self.robot.ShowReal
            self.previous_show_visual = self.robot.ShowVisual
            self.previous_show_collision = self.robot.ShowCollision
        except AttributeError:
            pass

    def onChanged(self, feature: DO, prop: str) -> None:
        print(f'Robot::onChanged({feature.Name}, {prop})')
        if not hasattr(self, 'robot'):
            # Implementation note: happens but how is it possible?
            print('self has no "robot"') # DEBUG
            return
        # 'Group' must be treated specially to avoid recursion when calling
        # self.reset_group().
        # link_count_now = len(get_links(self.robot.Group))
        # if prop == 'Group' and (self.previous_link_count != link_count_now):
        #     self.previous_link_count = link_count_now
        #     self.reset_group()
        #     return
        # if prop in ['ShowReal', 'ShowVisual', 'ShowCollision']:
        #     self.reset_group()
        #     return
        if prop in ['Group', 'ShowReal', 'ShowVisual', 'ShowCollision']:
            self.reset_group()

    def reset_group(self):
        print('Robot::reset_group()')

        if ((not hasattr(self.robot, 'ShowReal'))
                or (not hasattr(self.robot, 'ShowVisual'))
                or (not hasattr(self.robot, 'ShowCollision'))):
            return

        links = get_links(self.robot.Group)  # ROS links.
        rest = [o for o in self.robot.Group if o not in links]

        # List of linked objects from all Ros::Link in robot.Group.
        current_linked_objects: List[DO] = []
        for l in links:
            for o in l.Group:
                current_linked_objects.append(o)
                # print(f'  current_linked_objects; {o.Name}: {hash(current_linked_objects[-1])}')

        # Add objects from selected components.
        all_linked_objects: List[DO] = []
        if self.robot.ShowReal:
            for l in links:
                all_linked_objects += _add_links_lod(l, l.Real, 'real')

        if self.robot.ShowVisual:
            for l in links:
                all_linked_objects += _add_links_lod(l, l.Visual, 'visual')

        if self.robot.ShowCollision:
            for l in links:
                all_linked_objects += _add_links_lod(l, l.Collision, 'collision')

        # Remove objects that do not belong to `all_linked_objects`.
        objects_to_remove = set(current_linked_objects) - set(all_linked_objects)
        for o in objects_to_remove:
            # print(f'Removing {o.Name}')
            self.robot.Document.removeObject(o.Name)
        # TODO?: doc.recompute() if objects_to_remove or (set(current_linked_objects) != set(all_linked_objects))

    def onDocumentRestored(self, obj):
        """Restore attributes because __init__ is not called on restore."""
        print('Robot::onDocumenRestored')
        obj.Proxy = self
        self.robot = obj
        self.type = 'Ros::Robot'
        self.previous_link_count = len(get_links(self.robot.Group))
        self.init_properties(obj)

    def __getstate__(self):
        return (self.type, self.previous_link_count)

    def __setstate__(self, state):
        if state:
            self.type, self.previous_link_count = state


class _ViewProviderRobot:
    """A view provider for the Robot container object """
    def __init__(self, vobj):
        vobj.Proxy = self

    def getIcon(self):
        # TODO: Solve why this doesn't work.
        # return 'ros_9dotslogo_color.svg'
        return str(ICON_PATH.joinpath('ros_9dotslogo_color.svg'))

    def attach(self, vobj):
        self.ViewObject = vobj
        self.robot = vobj.Object

    def updateData(self, obj, prop):
        return

    def onChanged(self, vobj, prop):
        return

    def doubleClicked(self, vobj):
        import FreeCADGui as fcgui
        gui_doc = vobj.Document
        if not gui_doc.getInEdit():
            gui_doc.setEdit(vobj.Object.Name)
        else:
            error('Task dialog already active')
        return True

    def setEdit(self, vobj, mode):
        import FreeCADGui as fcgui
        from .task_panel_robot import TaskPanelRobot
        task_panel = TaskPanelRobot(self.robot)
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


def makeRobot(name):
    """Add a Ros::Robot to the current document."""
    doc = fc.activeDocument()
    if not doc:
        return
    obj = doc.addObject('App::DocumentObjectGroupPython', name)
    Robot(obj)

    if fc.GuiUp:
        _ViewProviderRobot(obj.ViewObject)

    doc.recompute()
    return obj
