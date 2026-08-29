"""
Paste this whole file into Maya's Python Script Editor and run it.

Select a projection node (in the Node Editor or Hypershade) and run the
script. It inserts a UV distortion network between the projection's image
texture and its UV source, adding a subtle psychedelic curve to the
projected result. Any standalone 2D texture (file, ramp, checker, ...)
can be distorted the same way by selecting it directly.

The distortion warps the texture lookup per sample:

    uv' = uv + amount * (noise(uv) - 0.5)

using two decorrelated Maya `noise` textures for the U and V offsets, so
straight lines in the source texture become smooth flowing curves. Only
standard Maya shading nodes are created, so the effect renders anywhere
Maya's classic texture nodes do and needs no plug-ins.

Everything is driven by keyable attributes on a single `uvDistort#_CTRL`
node (a renamed plusMinusAverage that performs the final UV sum), so the
effect can be tuned from the Channel Box, animated, or adjusted with the
slider window this script opens. Re-running the script with a distorted
projection selected reopens the window instead of stacking a second
distortion. Press "Remove This Distortion" to delete the created nodes
and restore the original UV wiring exactly.
"""

import maya.cmds as cmds

PREFIX = "uvDistort"
WINDOW = PREFIX + "Window"

# Decorrelates the V-offset noise from the U-offset noise by evaluating it
# at a different point along the noise time axis.
FLOW_SHIFT = 19.1

AMOUNT_DEFAULT = 0.03
CURVE_SCALE_DEFAULT = 3.0
DETAIL_DEFAULT = 2
FLOW_DEFAULT = 0.0

# Matches the noise texture's noiseType enum order.
CURVE_STYLES = "Smooth (Perlin):Billow:Wave:Wispy:SpaceTime"

_active_controller = None


def _is_controller(node):
    return cmds.attributeQuery("distortAmountU", node=node, exists=True)


def _texture_uv_source(texture):
    plugs = cmds.listConnections(
        texture + ".uvCoord", source=True, destination=False, plugs=True
    )
    return plugs[0] if plugs else None


def _controller_for_texture(texture):
    source = _texture_uv_source(texture)
    if source:
        node = source.split(".")[0]
        if _is_controller(node):
            return node
    return None


def _resolve_selection():
    """Return (texture, existing_controller) for the current selection."""
    for node in cmds.ls(selection=True) or []:
        if _is_controller(node):
            texture = _controller_texture(node)
            return texture, node
        node_type = cmds.nodeType(node)
        if node_type == "projection":
            sources = cmds.listConnections(
                node + ".image", source=True, destination=False
            )
            if not sources:
                raise RuntimeError(
                    "Projection {} has no texture connected to its "
                    "Image attribute.".format(node)
                )
            texture = sources[0]
        elif "texture/2d" in ":".join(cmds.getClassification(node_type)):
            texture = node
        else:
            continue
        if not cmds.attributeQuery("uvCoord", node=texture, exists=True):
            raise RuntimeError(
                "{} has no uvCoord attribute to distort.".format(texture)
            )
        return texture, _controller_for_texture(texture)
    raise RuntimeError(
        "Select a projection node, a 2D texture, or an existing "
        "{}#_CTRL node first.".format(PREFIX)
    )


def _controller_texture(controller):
    plugs = cmds.listConnections(
        controller + ".output2D", source=False, destination=True, plugs=True
    ) or []
    for plug in plugs:
        node, attr = plug.split(".", 1)
        if attr.startswith("uvCoord"):
            return node
    return None


def _next_controller_name():
    index = 1
    while cmds.objExists("{}{}_CTRL".format(PREFIX, index)):
        index += 1
    return index, "{}{}_CTRL".format(PREFIX, index)


def _tag(controller, node):
    """Mark node as owned by controller so removal can find it."""
    cmds.addAttr(node, longName="uvDistortTag", attributeType="message")
    cmds.connectAttr(controller + ".message", node + ".uvDistortTag")


def _add_float(node, name, nice, default, minimum=None):
    kwargs = {"defaultValue": default, "keyable": True}
    if minimum is not None:
        kwargs["minValue"] = minimum
    cmds.addAttr(
        node, longName=name, niceName=nice, attributeType="float", **kwargs
    )


def build_distortion(texture):
    """Insert the distortion network in front of texture's UV lookup."""
    index, controller = _next_controller_name()

    def named(suffix, node):
        return cmds.rename(node, "{}{}_{}".format(PREFIX, index, suffix))

    original = _texture_uv_source(texture)

    controller = cmds.rename(
        cmds.shadingNode("plusMinusAverage", asUtility=True), controller
    )
    _add_float(controller, "distortAmountU", "Distort Amount U",
               AMOUNT_DEFAULT, minimum=0.0)
    _add_float(controller, "distortAmountV", "Distort Amount V",
               AMOUNT_DEFAULT, minimum=0.0)
    _add_float(controller, "curveScale", "Curve Scale",
               CURVE_SCALE_DEFAULT, minimum=0.0)
    _add_float(controller, "detail", "Detail", DETAIL_DEFAULT, minimum=1.0)
    _add_float(controller, "flow", "Flow", FLOW_DEFAULT)
    cmds.addAttr(
        controller, longName="curveStyle", niceName="Curve Style",
        attributeType="enum", enumName=CURVE_STYLES, keyable=True,
    )
    cmds.addAttr(controller, longName="restorePlug", dataType="string")
    cmds.setAttr(
        controller + ".restorePlug", original or "", type="string"
    )

    # Base UV source: reuse the texture's existing place2dTexture, or give
    # it one so repeat/offset/rotate controls stay available.
    if original:
        base_plug = original
    else:
        place = named(
            "place2d", cmds.shadingNode("place2dTexture", asUtility=True)
        )
        _tag(controller, place)
        if not cmds.listConnections(texture + ".uvFilterSize"):
            cmds.connectAttr(
                place + ".outUvFilterSize", texture + ".uvFilterSize"
            )
        base_plug = place + ".outUV"

    noise_u = named("noiseU", cmds.shadingNode("noise", asTexture=True))
    noise_v = named("noiseV", cmds.shadingNode("noise", asTexture=True))
    for noise in (noise_u, noise_v):
        _tag(controller, noise)
        cmds.setAttr(noise + ".amplitude", 1.0)
        # The noises must be told which UV they are being sampled at: an
        # unconnected uvCoord does not inherit the projection's UV context
        # and evaluates as a constant, which turns the warp into a uniform
        # offset and makes frequency changes invisible.
        cmds.connectAttr(base_plug, noise + ".uvCoord")
        cmds.connectAttr(controller + ".curveScale", noise + ".frequency")
        cmds.connectAttr(controller + ".detail", noise + ".depthMax")
        cmds.connectAttr(controller + ".curveStyle", noise + ".noiseType")

    # U and V sample the same noise field at different times so their
    # offsets stay independent; animating flow slides both together.
    flow_shift = named(
        "flowShift", cmds.shadingNode("addDoubleLinear", asUtility=True)
    )
    _tag(controller, flow_shift)
    cmds.setAttr(flow_shift + ".input2", FLOW_SHIFT)
    cmds.connectAttr(controller + ".flow", noise_u + ".time")
    cmds.connectAttr(controller + ".flow", flow_shift + ".input1")
    cmds.connectAttr(flow_shift + ".output", noise_v + ".time")

    center = named(
        "center", cmds.shadingNode("plusMinusAverage", asUtility=True)
    )
    _tag(controller, center)
    cmds.setAttr(center + ".operation", 2)  # subtract
    cmds.connectAttr(
        noise_u + ".outColorR", center + ".input2D[0].input2Dx"
    )
    cmds.connectAttr(
        noise_v + ".outColorR", center + ".input2D[0].input2Dy"
    )
    cmds.setAttr(center + ".input2D[1]", 0.5, 0.5, type="float2")

    scale = named(
        "scale", cmds.shadingNode("multiplyDivide", asUtility=True)
    )
    _tag(controller, scale)
    cmds.connectAttr(center + ".output2Dx", scale + ".input1X")
    cmds.connectAttr(center + ".output2Dy", scale + ".input1Y")
    cmds.connectAttr(controller + ".distortAmountU", scale + ".input2X")
    cmds.connectAttr(controller + ".distortAmountV", scale + ".input2Y")

    cmds.connectAttr(base_plug, controller + ".input2D[0]")
    cmds.connectAttr(scale + ".outputX", controller + ".input2D[1].input2Dx")
    cmds.connectAttr(scale + ".outputY", controller + ".input2D[1].input2Dy")
    cmds.connectAttr(
        controller + ".output2D", texture + ".uvCoord", force=True
    )
    return controller


def remove_distortion(controller):
    """Delete controller's network and restore the original UV wiring."""
    texture = _controller_texture(controller)
    restore = cmds.getAttr(controller + ".restorePlug") or ""
    owned = []
    for plug in cmds.listConnections(
        controller + ".message", source=False, destination=True, plugs=True
    ) or []:
        node, attr = plug.split(".", 1)
        if attr == "uvDistortTag":
            owned.append(node)
    cmds.delete([controller] + owned)
    if texture and restore and cmds.objExists(restore.split(".")[0]):
        cmds.connectAttr(restore, texture + ".uvCoord", force=True)
    return texture


def apply_uv_distortion():
    """Distort the selection, or rebind the window if already distorted."""
    global _active_controller
    texture, controller = _resolve_selection()
    if controller is None:
        controller = build_distortion(texture)
    _active_controller = controller
    cmds.select(controller, replace=True)
    show_window()
    return controller


def _remove_active(*_):
    global _active_controller
    if not _active_controller or not cmds.objExists(_active_controller):
        raise RuntimeError("No active distortion to remove.")
    texture = remove_distortion(_active_controller)
    _active_controller = None
    if cmds.window(WINDOW, exists=True):
        cmds.deleteUI(WINDOW)
    if texture:
        print("Removed UV distortion from {}.".format(texture))


def _apply_selected(*_):
    apply_uv_distortion()


def _select_controller(*_):
    if _active_controller and cmds.objExists(_active_controller):
        cmds.select(_active_controller, replace=True)


def show_window():
    if cmds.window(WINDOW, exists=True):
        cmds.deleteUI(WINDOW)
    controller = _active_controller
    bound = controller is not None and cmds.objExists(controller)
    cmds.window(WINDOW, title="UV Distort", sizeable=True)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=6, columnOffset=("both", 8))

    if bound:
        texture = _controller_texture(controller) or "?"
        cmds.text(
            label="{}  →  {}".format(controller, texture),
            align="left", font="boldLabelFont",
        )

        def slider(label, attr, minimum, maximum, field_max, field_min=None):
            def assign(value, attr=attr):
                cmds.setAttr(controller + "." + attr, value)
            cmds.floatSliderGrp(
                label=label, field=True,
                minValue=minimum, maxValue=maximum,
                fieldMinValue=field_min if field_min is not None else minimum,
                fieldMaxValue=field_max,
                value=cmds.getAttr(controller + "." + attr),
                dragCommand=assign, changeCommand=assign,
                columnWidth3=(90, 60, 200), adjustableColumn=3,
            )

        slider("Amount U", "distortAmountU", 0.0, 0.2, 10.0)
        slider("Amount V", "distortAmountV", 0.0, 0.2, 10.0)
        slider("Curve Scale", "curveScale", 0.0, 12.0, 100.0)
        slider("Detail", "detail", 1.0, 8.0, 8.0)
        slider("Flow", "flow", -10.0, 10.0, 10000.0, field_min=-10000.0)

        def assign_style(_):
            cmds.setAttr(
                controller + ".curveStyle",
                cmds.optionMenuGrp(style_menu, query=True, select=True) - 1,
            )

        style_menu = cmds.optionMenuGrp(
            label="Curve Style", changeCommand=assign_style,
            columnWidth2=(90, 200),
        )
        for item in CURVE_STYLES.split(":"):
            cmds.menuItem(label=item)
        cmds.optionMenuGrp(
            style_menu, edit=True,
            select=cmds.getAttr(controller + ".curveStyle") + 1,
        )
        cmds.button(
            label="Select Controller", command=_select_controller
        )
        cmds.button(
            label="Remove This Distortion", command=_remove_active
        )
    else:
        cmds.text(
            label="Select a projection node or 2D texture, then press "
            "Distort Selected.",
            align="left", wordWrap=True,
        )
    cmds.button(label="Distort Selected", command=_apply_selected)
    cmds.separator(style="none", height=2)
    cmds.showWindow(WINDOW)


if __name__ == "__main__":
    try:
        apply_uv_distortion()
    except RuntimeError:
        if _active_controller and cmds.objExists(_active_controller):
            show_window()
        else:
            raise
