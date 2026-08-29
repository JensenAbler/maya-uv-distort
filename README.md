# Maya UV Distort

A single Python script for Autodesk Maya that adds a subtle psychedelic
curve to a projected texture by warping its UV lookup inside the shading
network.

Select a `projection` node in the Node Editor (or Hypershade) and run the
script. It inserts a distortion network between the projection's image
texture and its UV source, so straight lines in the source image flow
into smooth curves in the projected result. Any standalone 2D texture
(`file`, `ramp`, `checker`, ...) can be distorted the same way by
selecting the texture itself.

Only standard Maya shading nodes are created (`noise`,
`plusMinusAverage`, `multiplyDivide`, `addDoubleLinear`,
`place2dTexture`), so no plug-ins are required and the effect renders
anywhere Maya's classic texture nodes do.

## Usage

1. Open Maya and select the projection node (or a 2D texture) in the
   Node Editor or Hypershade.
2. Open the Python tab of Maya's Script Editor.
3. Copy and run the complete contents of
   [`maya_uv_distort.py`](maya_uv_distort.py).
4. Adjust the sliders in the **UV Distort** window, or edit the custom
   attributes on the created `uvDistort#_CTRL` node in the Channel Box.
5. To animate the effect, key the controller attributes — keying or
   linking **Flow** to time makes the curves drift continuously.

Re-running the script with an already-distorted projection selected
reopens the control window instead of stacking a second distortion.
Several independent distortions can coexist in one scene; each gets its
own numbered controller.

## Parameters

All parameters live as keyable attributes on `uvDistort#_CTRL`.

| Attribute | Purpose |
| --- | --- |
| `distortAmountU` | UV offset strength in U, in UV units; unbounded, 0 disables, negative inverts |
| `distortAmountV` | UV offset strength in V, in UV units; unbounded |
| `curveScale` | Noise frequency; lower values give broader, lazier curves |
| `detail` | Noise octaves; 1–2 stays smooth, higher adds finer wobble |
| `flow` | Slides both noise fields through time; animate for drift |
| `curveStyle` | Noise character: Smooth (Perlin), Billow, Wave, Wispy, or SpaceTime |

The defaults (`0.03` amount, curve scale `3`, detail `2`, Perlin) give a
gentle heat-haze bend. For a stronger melt, raise the amounts toward
`0.1`. The **Wave** style pushes the look toward sinusoidal, moiré-like
curves; **SpaceTime** animates on its own as **Flow** changes.

## How it works

The distortion warps the texture lookup per shading sample:

```
uv' = uv + amount * (noise(uv) - 0.5)
```

Two `noise` textures evaluated at different points along the noise time
axis supply decorrelated U and V offsets. The offsets are centered,
scaled by the amount attributes, and summed with the base UV coordinate
by the controller node (a `plusMinusAverage`), whose output drives the
texture's `uvCoord`.

Because a projection node evaluates its image texture with the UVs it
computes from the 3D placement, the inserted network warps those
projected coordinates before the image is sampled — the projection
placement itself is untouched, so it can still be moved and interactively
placed as usual.

If the texture already had a `place2dTexture`, it is kept as the base UV
source and its repeat/offset/rotate controls continue to work. If it had
none, the script creates one.

## Removing a distortion

Press **Remove This Distortion** in the control window, or select the
controller (or the distorted projection/texture), run the script to bind
the window, and press it there. The created nodes are deleted and the
texture's original `uvCoord` wiring is restored exactly.

## Notes

- The warped lookup can sample outside 0–1; the texture's wrap settings
  decide what appears there (file textures tile by default).
- If a distorted file texture renders blurrier than expected, reduce the
  file node's filter amount — heavily warped UV derivatives can inflate
  the filter size.
- Viewport 2.0 may preview complex texture networks approximately; judge
  the final look in a render.
- The `layeredTexture` node has no `uvCoord` input and cannot be
  distorted directly; distort the textures inside it instead.

## License

MIT
