' Retro TV for Roku: a port of the browser viewer (../docker/web/app/js/app.js).
'
' Same screens, themes, fonts and layout: the guide is drawn in the viewer's
' 853x480 design units and scaled by K = 2.25 to fill 1920x1080.
'
' Remote, mapped to the viewer's keyboard actions:
'   Guide     arrows move (held Up / Down speed up; Down on the last channel
'             wraps to the first), OK watches, Play/Pause opens show details,
'             Replay (or *) opens settings, Up from the top row selects the
'             settings cog (Up again wraps to the last channel), Rewind /
'             Fast-forward page through channels, Back returns to the
'             picture (or leaves the app).
'   Watching  Up / Down change channel, OK shows the channel bar (then
'             activates its highlighted button; Left / Right pick one),
'             Back opens the guide.
'   Details   OK or the buttons, Up / Down scroll, Back closes.
'   Settings  Up / Down pick, Left / Right / OK change, Back closes. On
'             Theme they open the theme picker: arrows move, OK takes it.
'
' Kept in the Roku's registry (section "RetroTV"): server, channel (the
' last one watched, by number), quality ("sd" or "hd"), theme (an id from
' themeIds()).

' ---- design units -------------------------------------------------------------

function KK() as float
    return 2.25
end function

' Design pixels to screen pixels.
function px(v as dynamic) as integer
    return Int(v * 2.25 + 0.5)
end function

' ---- themes (the viewer's js/themes.js and the [data-theme] blocks in guide.css) ----
' Colour names keep the Cable theme's words whatever the colour is. "accent"
' is the accent used as text (channel line, clock, messages): yellow in
' Cable, cyan in Vaporwave, where pink text would smear on a composite CRT.
'
' A Roku draws square, flat rectangles: where the viewer has a gradient the
' theme here has its middle colour, and the rounded, glossy, bevelled and
' framed cells are small stretchable pictures (images/*.9.png, made by
' tools/render-splash): "shape" ones are white and tinted with the cell's
' colour, "bevel" is laid over a flat cell, "prevue" carries its own fill.

function themeIds() as object
    return ["cable", "vapor", "digital", "satellite", "dvr", "mediacenter", "aqua", "settop", "listings"]
end function

function themeTable() as object
    if m.themeTable <> invalid then return m.themeTable
    t = {}
    t.cable = {
        label: "Cable",
        help: "The late-90s cable guide: navy and yellow, flat cells. The splash is the little television.",
        colors: {
            navy: "0x0A1240FF", program: "0x0F2A7AFF", channel: "0x1C3FA8FF",
            timebar: "0x5A7FE0FF", yellow: "0xF2C200FF", soft: "0xCFE0FFFF",
            white: "0xFFFFFFFF", gap: "0x000000FF", accent: "0xF2C200FF"
        },
        splash: "pkg:/images/splash_fhd.png"
    }
    t.vapor = {
        label: "Vaporwave",
        help: "Purple cells, pink highlights, cyan text. The splash is a sunset over a neon grid.",
        colors: {
            navy: "0x0D0624FF", program: "0x2A0A4EFF", channel: "0x4A1278FF",
            timebar: "0x7B3FC4FF", yellow: "0xFF3FA4FF", soft: "0xD9C8FFFF",
            white: "0xFFFFFFFF", gap: "0x000000FF", accent: "0x19E6FFFF"
        },
        display: "pkg:/fonts/Audiowide-Regular.ttf"
    }
    t.digital = {
        label: "Digital Cable",
        help: "A 2000s digital cable box: black and deep blue, rounded bars, a light-blue highlight.",
        colors: {
            navy: "0x000814FF", program: "0x1D4A9AFF", channel: "0x2A2F39FF",
            timebar: "0x444D5BFF", yellow: "0x7CC0FFFF", soft: "0xB9D6FFFF",
            white: "0xFFFFFFFF", gap: "0x000814FF", accent: "0x8FC8FFFF",
            seltext: "0x03112EFF", slottext: "0xE6EEFCFF", frame: "0x4AA3FFFF"
        },
        style: "shape", shape: "pkg:/images/round_m.9.png", cellSize: 14,
        regular: "pkg:/fonts/Arimo-Regular.ttf", bold: "pkg:/fonts/Arimo-Bold.ttf"
    }
    t.satellite = {
        label: "Satellite",
        help: "An early-2000s satellite receiver: navy into purple, rounded tabs, a gold highlight. The splash is a dish in orbit.",
        colors: {
            navy: "0x120A38FF", program: "0x233178FF", channel: "0x3B2285FF",
            timebar: "0x5848B5FF", yellow: "0xFFCE5CFF", soft: "0xC9CFF5FF",
            white: "0xFFFFFFFF", gap: "0x120A38FF", accent: "0xFFCE5CFF",
            seltext: "0x1A0D4AFF", frame: "0xFFCE5CFF"
        },
        style: "shape", shape: "pkg:/images/round_s.9.png", shapeChan: "pkg:/images/round_l.9.png", cellSize: 14,
        regular: "pkg:/fonts/Exo2-Regular.ttf", bold: "pkg:/fonts/Exo2-ExtraBold.ttf"
    }
    t.dvr = {
        label: "DVR",
        help: "A hard-disk recorder from around 2000: soft blues, rounded white pills, a green highlight and a friendly little TV.",
        colors: {
            navy: "0x23559FFF", program: "0xE9F0FBFF", channel: "0xFFFFFFFF",
            timebar: "0xFFD54AFF", yellow: "0x7ED957FF", soft: "0xE3ECFFFF",
            white: "0xFFFFFFFF", gap: "0x23559FFF", accent: "0xFFD54AFF",
            text: "0x173A80FF", slottext: "0x173A80FF", seltext: "0x134D12FF",
            clockfill: "0xFF7A7AFF", clocktext: "0x5E1212FF", frame: "0xFFFFFFFF"
        },
        style: "shape", shape: "pkg:/images/round_l.9.png", cellSize: 14,
        regular: "pkg:/fonts/Nunito-Regular.ttf", bold: "pkg:/fonts/Nunito-ExtraBold.ttf"
    }
    t.mediacenter = {
        label: "Media Center",
        help: "A 2005 living-room PC: glassy blue tiles, a green highlight, a thin face.",
        colors: {
            navy: "0x08356AFF", program: "0x1C4F86FF", channel: "0x2A5D95FF",
            timebar: "0x08356AFF", yellow: "0x52C244FF", soft: "0xB7E0FFFF",
            white: "0xFFFFFFFF", gap: "0x08356AFF", accent: "0x9FF07EFF",
            seltext: "0xFFFFFFFF", slottext: "0xB7E0FFFF",
            clockfill: "0x08356AFF", clocktext: "0xFFFFFFFF", frame: "0x9DB4CCFF"
        },
        style: "shape", shape: "pkg:/images/round_s.9.png", cellSize: 14,
        regular: "pkg:/fonts/OpenSans-Regular.ttf", bold: "pkg:/fonts/OpenSans-SemiBold.ttf",
        display: "pkg:/fonts/OpenSans-Light.ttf"
    }
    t.aqua = {
        label: "Aqua",
        help: "The Y2K desktop: light grey, white rounded cells, metal tabs and a blue gel highlight.",
        colors: {
            navy: "0xE3E7ECFF", program: "0xF4F6F9FF", channel: "0xC9CED5FF",
            timebar: "0xC9CED5FF", yellow: "0x4DAEF7FF", soft: "0x4C5868FF",
            white: "0x1D2A3AFF", gap: "0xFFFFFFFF", lines: "0xE3E7ECFF", accent: "0x1F78C8FF",
            seltext: "0x04305AFF", slottext: "0x3A4350FF", frame: "0x8F96A0FF"
        },
        style: "shape", shape: "pkg:/images/round_l.9.png", cellSize: 14,
        regular: "pkg:/fonts/Lato-Regular.ttf", bold: "pkg:/fonts/Lato-Bold.ttf"
    }
    t.settop = {
        label: "Set-Top Web",
        help: "A late-90s internet box on the TV: purple and black, chunky bevelled buttons, everything in capitals.",
        colors: {
            navy: "0x12082AFF", program: "0x3A2468FF", channel: "0x52348EFF",
            timebar: "0x6A4AA8FF", yellow: "0xFFBE3CFF", soft: "0xD9C8FFFF",
            white: "0xFFFFFFFF", gap: "0x07020FFF", accent: "0xFFBE3CFF",
            seltext: "0x2A1450FF", frame: "0x8F7BC0FF"
        },
        style: "bevel", cellSize: 14, upper: true,
        regular: "pkg:/fonts/ChakraPetch-Regular.ttf", bold: "pkg:/fonts/ChakraPetch-Bold.ttf",
        display: "pkg:/fonts/ArchivoBlack-Regular.ttf"
    }
    ' The id is still "listings" (the theme this one replaced), as in the viewer.
    t.listings = {
        label: "TV Guide",
        help: "The scrolling TV Guide Channel of the late 90s, as on channel 1: dark blue boxes in 3-D frames, yellow channels and times, grey listings in the Amiga font.",
        colors: {
            navy: "0x000030FF", program: "0x000051FF", channel: "0x000051FF",
            timebar: "0x263383FF", yellow: "0xCBD100FF", soft: "0xAAAAAAFF",
            white: "0xAAAAAAFF", gap: "0x000030FF", accent: "0xCBD100FF",
            text: "0xAAAAAAFF", slottext: "0xCBD100FF", chantext: "0xCBD100FF",
            clockfill: "0x263383FF", clocktext: "0xCBD100FF", seltext: "0x000030FF",
            frame: "0xAAAAAAFF", time: "0xCBD100FF"
        },
        style: "prevue", cellSize: 21, chanSize: 18, clockSize: 17, btnSize: 19,
        chanUpper: true, shadow: true, centerBar: true, info: [21, 25, 20, 20, 18, 20],
        regular: "pkg:/fonts/PrevueGrid.ttf", bold: "pkg:/fonts/PrevueGrid.ttf"
    }

    ' Whatever a theme leaves out is as in Cable.
    for each id in themeIds()
        th = t[id]
        c = th.colors
        setDefault(c, "text", c.white)
        setDefault(c, "seltext", c.navy)
        setDefault(c, "slottext", c.white)
        setDefault(c, "chantext", c.text)
        setDefault(c, "clockfill", c.yellow)
        setDefault(c, "clocktext", c.seltext)
        setDefault(c, "frame", c.yellow)
        setDefault(c, "lines", c.gap)
        setDefault(c, "time", c.white)
        setDefault(th, "style", "flat")
        setDefault(th, "shape", "")
        setDefault(th, "shapeChan", th.shape)
        setDefault(th, "regular", "pkg:/fonts/Cabin-Regular.ttf")
        setDefault(th, "bold", "pkg:/fonts/Cabin-Bold.ttf")
        setDefault(th, "display", th.bold)
        setDefault(th, "cellSize", 15)
        setDefault(th, "chanSize", th.cellSize)
        setDefault(th, "clockSize", th.cellSize)
        setDefault(th, "btnSize", 15)
        setDefault(th, "upper", false)
        setDefault(th, "chanUpper", th.upper)
        setDefault(th, "shadow", false)
        setDefault(th, "centerBar", false)
        setDefault(th, "info", [15, 21, 16, 16, 14, 18])
        setDefault(th, "splash", "pkg:/images/splash_" + id + "_fhd.jpg")
    end for
    m.themeTable = t
    return t
end function

sub setDefault(aa as object, key as string, value as dynamic)
    if not aa.DoesExist(key) then aa[key] = value
end sub

function theme() as object
    return m.T
end function

' Make a theme current: its colours for col(), its faces, a fresh font
' cache. The stage must be (re)built after this to show the change.
sub applyTheme(id as string)
    if themeTable()[id] = invalid then id = "cable"
    m.theme = id
    m.T = themeTable()[id]
    m.colors = m.T.colors
    m.fonts = {}
end sub

function col(name as string) as string
    return m.colors[name]
end function

' Capitals where the theme sets them (everything in Set-Top Web, the
' channel names in TV Guide).
function cellCase(text as string, isChan as boolean) as string
    if m.T.upper or (isChan and m.T.chanUpper) then return UCase(text)
    return text
end function

' A stretchable picture (9-patch) at a size, tinted unless tint is "".
function shapeIn(parent as object, x as integer, y as integer, w as integer, h as integer, uri as string, tint as string) as object
    p = CreateObject("roSGNode", "Poster")
    p.translation = [x, y]
    p.width = w
    p.height = h
    p.uri = uri
    if tint <> "" then p.blendColor = tint
    parent.appendChild(p)
    return p
end function

' A cell, button or settings row in the theme's shape, in screen pixels.
' kind: "show", "chan", "bar" (time bar), "clock", "sel" (highlight), "selchan".
' Text goes in as a child of what this returns.
function cellBox(parent as object, x as integer, y as integer, w as integer, h as integer, kind as string, color as string) as object
    th = m.T
    w = maxI(w, 0)
    if th.style = "flat" or w < 60 then return rect(parent, x, y, w, h, color)
    if th.style = "bevel" then
        r = rect(parent, x, y, w, h, color)
        shapeIn(r, 0, 0, w, h, "pkg:/images/bevel.9.png", "")
        return r
    end if
    if th.style = "prevue" then
        uri = "pkg:/images/prevue_row.9.png"
        if kind = "bar" or kind = "clock" then uri = "pkg:/images/prevue_bar.9.png"
        if kind = "sel" or kind = "selchan" then uri = "pkg:/images/prevue_sel.9.png"
        return shapeIn(parent, x, y, w, h, uri, "")
    end if
    uri = th.shape
    if kind = "chan" or kind = "selchan" then uri = th.shapeChan
    ' The big radius needs a cell as tall as a grid row; buttons take the middle one.
    if h < 58 and uri = "pkg:/images/round_l.9.png" then uri = "pkg:/images/round_m.9.png"
    return shapeIn(parent, x, y, w, h, uri, color)
end function

' TV Guide theme: a hard black copy of a label, down and right, under it.
' Call it once the label is complete (text, alignment) and is still the
' last child of its parent.
sub addShadow(l as object)
    if not m.T.shadow then return
    p = l.getParent()
    if p = invalid then return
    sh = CreateObject("roSGNode", "Label")
    copyLabel(sh, l)
    p.insertChild(sh, p.getChildCount() - 1)
end sub

sub copyLabel(sh as object, l as object)
    tr = l.translation
    sh.translation = [tr[0] + 4, tr[1] + 4]
    sh.width = l.width
    sh.height = l.height
    sh.font = l.font
    sh.color = "0x111111FF"
    sh.vertAlign = l.vertAlign
    sh.horizAlign = l.horizAlign
    sh.wrap = l.wrap
    sh.maxLines = l.maxLines
    sh.lineSpacing = l.lineSpacing
    sh.text = l.text
    sh.visible = l.visible
end sub

function HALF() as integer
    return 1800
end function

function INF() as integer
    return 2140000000
end function

' ---- start ----------------------------------------------------------------------

sub init()
    ' The guide layout for a 16:9 screen (computeLayout in the viewer).
    m.lay = {
        W: 853, H: 480,
        pv: { x: 8, y: 8, w: 256, h: 193 },
        info: { x: 274, y: 8, w: 571, h: 194 },
        gridTop: 210, chanW: 126, timeX: 128, timeW: 725, slots: 4, row: 29, rows: 8
    }
    m.lay.span = m.lay.slots * HALF()

    m.fonts = {}
    m.video = m.top.findNode("video")
    m.stage = m.top.findNode("stage")
    m.overlay = m.top.findNode("overlay")
    m.video.observeField("state", "onVideoState")
    m.top.findNode("bannerTimer").observeField("fire", "hideBanner")
    m.top.findNode("osdTimer").observeField("fire", "hideOsd")
    m.top.findNode("tickTimer").observeField("fire", "onTick")
    m.top.findNode("refreshTimer").observeField("fire", "refresh")
    m.top.findNode("retryTimer").observeField("fire", "refresh")
    m.holdTimer = m.top.findNode("holdTimer")
    m.holdTimer.observeField("fire", "onHoldTick")
    m.holdDir = 0
    m.holdTicks = 0
    m.top.findNode("tickTimer").control = "start"
    m.top.findNode("refreshTimer").control = "start"
    m.playRetry = CreateObject("roSGNode", "Timer")
    m.playRetry.duration = 3
    m.playRetry.observeField("fire", "retryPlay")

    m.reg = CreateObject("roRegistrySection", "RetroTV")
    m.S = {
        channels: [], hasHd: false, dataEnd: 0, guide: {},
        mode: "guide", setRow: 0, focusCh: 0, focusTime: now(), winStart: floorHalf(now()),
        rowTop: 0, tuned: -1, cog: false, detBtn: 0, banBtn: 0, tpIndex: 0, muted: false,
        loading: false, retrySecs: 5, playState: "idle"
    }
    m.quality = regRead("quality", "sd")
    applyTheme(regRead("theme", "cable"))

    buildStage()
    buildOverlay()
    buildSplash()
    placeVideo()
    m.top.setFocus(true)
    ' The theme's splash over the loading guide (the Cable one continues the
    ' start-up splash from the manifest without a cut).
    showSplash(2)

    m.server = regRead("server", "")
    if m.server = "" then
        askServer("")
    else
        refresh()
    end if
end sub

' ---- small helpers ------------------------------------------------------------

function now() as integer
    return CreateObject("roDateTime").AsSeconds()
end function

function floorHalf(t as integer) as integer
    return t - (t mod HALF())
end function

function clampI(v as integer, lo as integer, hi as integer) as integer
    if v < lo then return lo
    if v > hi then return hi
    return v
end function

function maxI(a as integer, b as integer) as integer
    if a > b then return a
    return b
end function

function minI(a as integer, b as integer) as integer
    if a < b then return a
    return b
end function

function font(size as float, bold as boolean) as object
    key = size.ToStr() + bold.ToStr()
    if m.fonts.DoesExist(key) then return m.fonts[key]
    f = CreateObject("roSGNode", "Font")
    if bold then
        f.uri = m.T.bold
    else
        f.uri = m.T.regular
    end if
    f.size = Int(size + 0.5)
    m.fonts[key] = f
    return f
end function

' The theme's face for show titles (Audiowide in Vaporwave, Archivo Black in Set-Top Web...).
function displayFont(size as float) as object
    return faceFont(m.T.display, size)
end function

' Any face at a size (the theme picker shows every theme in its own).
function faceFont(uri as string, size as float) as object
    key = uri + size.ToStr()
    if m.fonts.DoesExist(key) then return m.fonts[key]
    f = CreateObject("roSGNode", "Font")
    f.uri = uri
    f.size = Int(size + 0.5)
    m.fonts[key] = f
    return f
end function

' A rectangle in screen pixels.
function rect(parent as object, x as integer, y as integer, w as integer, h as integer, color as string) as object
    r = CreateObject("roSGNode", "Rectangle")
    r.translation = [x, y]
    r.width = maxI(w, 0)
    r.height = maxI(h, 0)
    r.color = color
    parent.appendChild(r)
    return r
end function

' A one-line label in screen pixels.
function label(parent as object, x as integer, y as integer, w as integer, h as integer, size as float, bold as boolean, color as string) as object
    l = CreateObject("roSGNode", "Label")
    l.translation = [x, y]
    l.width = maxI(w, 1)
    l.height = maxI(h, 1)
    l.font = font(size, bold)
    l.color = color
    l.vertAlign = "center"
    parent.appendChild(l)
    return l
end function

function regRead(key as string, fallback as string) as string
    if m.reg.Exists(key) then return m.reg.Read(key)
    return fallback
end function

sub regWrite(key as string, value as string)
    m.reg.Write(key, value)
    m.reg.Flush()
end sub

' ---- time text (the viewer uses the device's clock style) ----------------------

function fmtTime(t as integer) as string
    d = CreateObject("roDateTime")
    d.FromSeconds(t)
    d.ToLocalTime()
    h = d.GetHours()
    ampm = "AM"
    if h >= 12 then ampm = "PM"
    h = h mod 12
    if h = 0 then h = 12
    mm = d.GetMinutes().ToStr()
    if Len(mm) = 1 then mm = "0" + mm
    return h.ToStr() + ":" + mm + " " + ampm
end function

' "5:07 – 6:33 PM", or "11:30 AM – 12:30 PM" across noon.
function fmtRange(a as integer, b as integer) as string
    x = fmtTime(a)
    y = fmtTime(b)
    if Right(x, 2) = Right(y, 2) then x = Left(x, Len(x) - 3)
    return x + " – " + y
end function

function fmtDay(t as integer) as string
    d = CreateObject("roDateTime")
    d.FromSeconds(t)
    d.ToLocalTime()
    return Left(d.GetWeekday(), 3)
end function

' ---- the guide screen's nodes -------------------------------------------------

sub buildStage()
    lay = m.lay
    s = m.stage
    rect(s, 0, 0, 1920, 1080, col("navy"))

    ' Picture pbox: 2 px yellow frame, black inside, a hint until something plays.
    rect(s, px(lay.pv.x), px(lay.pv.y), px(lay.pv.w), px(lay.pv.h), col("frame"))
    rect(s, px(lay.pv.x + 2), px(lay.pv.y + 2), px(lay.pv.w - 4), px(lay.pv.h - 4), "0x000000FF")
    m.previewMsg = label(s, px(lay.pv.x + 8), px(lay.pv.y + lay.pv.h - 24), px(lay.pv.w - 16), px(18), 13 * KK(), false, col("soft"))
    m.previewMsg.text = "Pick a show to watch"

    ' Programme info beside the picture.
    ' (TV Guide theme: five black copies first, so they lie under the lines.)
    sz = m.T.info
    m.infoShadows = []
    if m.T.shadow then
        for i = 0 to 4
            sh = CreateObject("roSGNode", "Label")
            s.appendChild(sh)
            m.infoShadows.Push(sh)
        end for
    end if
    m.infoCh = label(s, 0, 0, 0, 0, sz[0] * KK(), true, col("accent"))
    m.infoTitle = label(s, 0, 0, 0, 0, sz[1] * KK(), true, col("white"))
    m.infoTitle.font = displayFont(sz[1] * KK())
    m.infoEp = label(s, 0, 0, 0, 0, sz[2] * KK(), true, col("soft"))
    m.infoTime = label(s, 0, 0, 0, 0, sz[3] * KK(), true, col("time"))
    m.infoPlot = CreateObject("roSGNode", "Label")
    m.infoPlot.font = font(sz[4] * KK(), false)
    m.infoPlot.color = col("soft")
    m.infoPlot.wrap = true
    m.infoPlot.lineSpacing = px(sz[5]) - Int(sz[4] * KK() * 1.2)
    s.appendChild(m.infoPlot)

    ' Settings cog, top right of the info area.
    m.cog = CreateObject("roSGNode", "Poster")
    m.cog.uri = "pkg:/images/cog.png"
    m.cog.blendColor = col("soft")
    m.cog.translation = [px(lay.info.x + lay.info.w - 28 + 3), px(lay.info.y - 3 + 3)]
    m.cog.width = px(24)
    m.cog.height = px(24)
    s.appendChild(m.cog)

    ' Grid: black background (the 2 px lines), cells drawn on every render.
    rect(s, 0, px(lay.gridTop), 1920, px(lay.row * (lay.rows + 1)), col("gap"))
    m.gridCells = CreateObject("roSGNode", "Group")
    m.gridCells.translation = [0, px(lay.gridTop)]
    s.appendChild(m.gridCells)
    m.gridMsgBox = rect(s, 0, px(lay.gridTop + 2 + lay.row), 1920, px(27), col("program"))
    m.gridMsg = label(m.gridMsgBox, px(7), 0, 1920 - px(14), px(27), 15 * KK(), true, col("text"))
    m.gridMsg.text = "Loading the guide…"

    ' Show details and settings, over the grid.
    m.details = CreateObject("roSGNode", "Group")
    m.details.visible = false
    s.appendChild(m.details)
    m.settings = CreateObject("roSGNode", "Group")
    m.settings.visible = false
    s.appendChild(m.settings)
    m.picker = CreateObject("roSGNode", "Group")
    m.picker.visible = false
    s.appendChild(m.picker)
end sub

' After a theme change: draw the stage again in the new colours and put the
' current screen back as it was.
sub rebuildStage()
    m.stage.removeChildrenIndex(m.stage.getChildCount(), 0)
    buildStage()
    m.tuning.color = col("soft")
    m.previewMsg.visible = m.S.tuned < 0
    m.gridMsgBox.visible = m.S.channels.Count() = 0
    m.details.visible = m.S.mode = "details"
    m.settings.visible = m.S.mode = "settings"
    if m.S.mode = "settings" then renderSettings()
    m.picker.visible = m.S.mode = "themes"
    if m.S.mode = "themes" then renderPicker()
    placeVideo()
    render()
end sub

' ---- splash: the theme's scene over everything for a moment --------------------
' On start (2 s over the loading guide) and after a theme change. A still
' picture of the same scene the browser viewer draws (js/splash.js).

sub buildSplash()
    m.splash = m.top.findNode("splash")
    m.splashImg = m.top.findNode("splashImg")
    m.splashFade = m.top.findNode("splashFade")
    m.splashFade.observeField("state", "onSplashFade")
    m.top.findNode("splashTimer").observeField("fire", "fadeSplash")
end sub

sub showSplash(secs as float)
    m.splashFade.control = "stop"
    m.splashImg.uri = m.T.splash
    m.splash.opacity = 1
    m.splash.visible = true
    t = m.top.findNode("splashTimer")
    t.duration = secs
    t.control = "stop"
    t.control = "start"
end sub

sub fadeSplash()
    m.splashFade.control = "start"
end sub

sub onSplashFade()
    if m.splashFade.state = "stopped" then m.splash.visible = false
end sub

' Lay out the info column (a flex column in the viewer: empty lines collapse).
sub renderInfoLayout(ep as string, time as string, plot as string)
    lay = m.lay
    sz = m.T.info
    x = px(lay.info.x)
    w = px(lay.info.w)
    y = lay.info.y
    placeLine(m.infoCh, x, y, w - px(34), sz[0])
    y = y + Int(sz[0] * 1.2) + 2
    placeLine(m.infoTitle, x, y, w, sz[1])
    y = y + Int(sz[1] * 1.2) + 2
    m.infoEp.visible = ep <> ""
    if ep <> "" then
        placeLine(m.infoEp, x, y, w, sz[2])
        y = y + Int(sz[2] * 1.2)
    end if
    m.infoTime.visible = time <> ""
    if time <> "" then
        y = y + 4
        placeLine(m.infoTime, x, y, w, sz[3])
        y = y + Int(sz[3] * 1.2) + 4
    end if
    room = lay.info.y + lay.info.h - y
    lines = maxI(1, Int(room / sz[5]))
    m.infoPlot.translation = [x, px(y)]
    m.infoPlot.width = w
    m.infoPlot.height = px(lines * sz[5])
    m.infoPlot.maxLines = lines
    m.infoPlot.text = plot
    if m.infoShadows.Count() = 5 then
        lines5 = [m.infoCh, m.infoTitle, m.infoEp, m.infoTime, m.infoPlot]
        for i = 0 to 4
            copyLabel(m.infoShadows[i], lines5[i])
        end for
    end if
end sub

sub placeLine(l as object, x as integer, y as integer, w as integer, size as integer)
    l.translation = [x, px(y)]
    l.width = w
    l.height = px(size * 1.2)
end sub

' ---- overlay: tuning text, channel bar, short messages -----------------------

sub buildOverlay()
    m.tuning = CreateObject("roSGNode", "Label")
    m.tuning.color = col("soft")
    m.tuning.visible = false
    m.overlay.appendChild(m.tuning)
    m.banner = CreateObject("roSGNode", "Group")
    m.banner.visible = false
    m.overlay.appendChild(m.banner)
    m.osd = CreateObject("roSGNode", "Group")
    m.osd.visible = false
    m.overlay.appendChild(m.osd)
end sub

' The picture's pbox: the corner pbox in the guide, the whole screen while
' watching (4:3 standard or 16:9 HD, centred).
function pictureBox() as object
    if m.S.mode = "full" then
        if playingHd() then return { x: 0, y: 0, w: 1920, h: 1080 }
        return { x: 240, y: 0, w: 1440, h: 1080 }
    end if
    lay = m.lay
    return { x: px(lay.pv.x + 2), y: px(lay.pv.y + 2), w: px(lay.pv.w - 4), h: px(lay.pv.h - 4) }
end function

sub placeVideo()
    if m.S.mode = "full" then
        m.video.translation = [0, 0]
        m.video.width = 1920
        m.video.height = 1080
    else
        b = pictureBox()
        m.video.translation = [b.x, b.y]
        m.video.width = b.w
        m.video.height = b.h
    end if
    placeTuning()
end sub

' "Tuning to ..." along the bottom of the picture, sized to it (32 of 480).
sub placeTuning()
    b = pictureBox()
    u = b.h / 480
    m.tuning.font = font(32 * u, false)
    m.tuning.translation = [b.x + Int(8 * u), b.y + b.h - Int(50 * u)]
    m.tuning.width = b.w - Int(16 * u)
    m.tuning.height = Int(44 * u)
    m.tuning.vertAlign = "center"
end sub

' ---- address of the server -----------------------------------------------------

sub askServer(current as string)
    dialog = CreateObject("roSGNode", "StandardKeyboardDialog")
    dialog.title = "ErsatzTV address"
    dialog.message = ["The address of the TV server on your network,", "for example 192.168.1.20:8409"]
    dialog.buttons = ["OK"]
    text = current
    if text = "" then text = "http://"
    dialog.text = text
    dialog.observeField("buttonSelected", "onServerEntered")
    m.top.dialog = dialog
end sub

sub onServerEntered()
    text = m.top.dialog.text.Trim()
    m.top.dialog.close = true
    if Left(text, 4) <> "http" then text = "http://" + text
    while Right(text, 1) = "/"
        text = Left(text, Len(text) - 1)
    end while
    regWrite("server", text)
    m.server = text
    m.S.channels = []
    refresh()
end sub

' ---- loading the guide (channels.m3u + xmltv.xml) ------------------------------

sub refresh()
    if m.S.loading or m.server = "" then return
    m.S.loading = true
    m.chTask = CreateObject("roSGNode", "ChannelsTask")
    m.chTask.server = m.server
    m.chTask.observeField("channels", "onChannels")
    m.chTask.observeField("error", "onLoadError")
    m.chTask.control = "run"
end sub

sub onChannels()
    m.gTask = CreateObject("roSGNode", "GuideTask")
    m.gTask.server = m.server
    m.gTask.observeField("guide", "onGuideData")
    m.gTask.observeField("error", "onLoadError")
    m.gTask.control = "run"
end sub

sub onLoadError()
    m.S.loading = false
    if m.S.channels.Count() = 0 then
        m.gridMsgBox.visible = true
        m.gridMsg.text = "Can't reach the TV server. Trying again…  (Replay: change the address)"
        t = m.top.findNode("retryTimer")
        t.duration = m.S.retrySecs
        t.control = "start"
        m.S.retrySecs = minI(60, m.S.retrySecs * 2)
    end if
end sub

sub onGuideData()
    first = m.S.channels.Count() = 0
    focusNum = ""
    if not first then focusNum = m.S.channels[m.S.focusCh].num
    tunedNum = ""
    if m.S.tuned >= 0 then tunedNum = m.S.channels[m.S.tuned].num

    ' HD twins: group "HD", numbered 1000 above the channel they mirror
    ' (1 -> 1001). The older +100 numbering is still recognised; the first
    ' offset that lands on a channel wins.
    sd = {}
    for each c in m.chTask.channels
        if c.group <> "HD" then sd[c.num] = true
    end for
    hd = {}
    for each c in m.chTask.channels
        if c.group = "HD" then
            for each offset in [1000, 100]
                key = (c.n - offset).ToStr()
                if sd.DoesExist(key) and not hd.DoesExist(key) then
                    hd[key] = c.num
                    exit for
                end if
            end for
        end if
    end for
    chans = []
    for each c in m.chTask.channels
        if c.group <> "HD" then
            entry = { num: c.num, n: c.n, name: c.name, id: c.id, hd: "" }
            if hd.DoesExist(c.num) then entry.hd = hd[c.num]
            chans.Push(entry)
        end if
    end for
    m.S.channels = chans
    m.S.hasHd = hd.Count() > 0
    m.S.guide = m.gTask.guide
    dataEnd = 0
    for each id in m.S.guide
        cells = m.S.guide[id]
        if cells.Count() > 0 then dataEnd = maxI(dataEnd, cells[cells.Count() - 1].ends)
    end for
    m.S.dataEnd = dataEnd
    m.S.loading = false
    m.S.retrySecs = 5

    if first then focusNum = regRead("channel", "")
    m.S.focusCh = 0
    m.S.tuned = -1
    for i = 0 to chans.Count() - 1
        if chans[i].num = focusNum then m.S.focusCh = i
        if chans[i].num = tunedNum then m.S.tuned = i
    end for
    if chans.Count() = 0 then
        m.gridMsg.text = "The server has no channels."
        return
    end if
    m.gridMsgBox.visible = false
    ' Start of a visit: the channel watched last time (the first one on a
    ' first visit) starts playing in the corner box. The guide stays up.
    if first and m.S.tuned < 0 then tune(m.S.focusCh)
    render()
end sub

' ---- cells (cellAt in the viewer) ------------------------------------------------

function cellAt(ch as object, t as integer) as object
    cells = m.S.guide[ch.id]
    if cells = invalid then cells = []
    lo = 0
    hi = cells.Count() - 1
    while lo <= hi
        md = Int((lo + hi) / 2)
        if t < cells[md].start then
            hi = md - 1
        else if t >= cells[md].ends then
            lo = md + 1
        else
            return cells[md]
        end if
    end while
    a = -INF()
    b = INF()
    if hi >= 0 then a = cells[hi].ends
    if lo < cells.Count() then b = cells[lo].start
    return { gap: true, title: "No information", items: [], start: a, ends: b }
end function

function programmeAt(ch as object, t as integer) as object
    cell = cellAt(ch, t)
    for each p in cell.items
        if t >= p.start and t < p.ends then return p
    end for
    return invalid
end function

function cellLabel(cell as object) as string
    if cell.items.Count() > 1 then return cell.title + " · " + cell.items.Count().ToStr() + " shorts"
    return cell.title
end function

' The info lines for a cell (describe in the viewer).
function describe(cell as object) as object
    ep = ""
    plot = ""
    rating = ""
    if cell.items.Count() > 0 then rating = cell.items[0].rating
    if cell.items.Count() = 1 then
        one = cell.items[0]
        if one.sub <> "" then
            ep = Chr(34) + one.sub + Chr(34)
        else if one.movie and one.year <> "" then
            ep = one.year
        end if
        plot = one.desc
    else if cell.items.Count() > 1 then
        ep = cell.items.Count().ToStr() + " shorts"
        names = []
        for each p in cell.items
            if p.sub <> "" then
                names.Push(p.sub)
            else
                names.Push(p.title)
            end if
        end for
        plot = names.Join(" · ")
    end if
    time = ""
    if cell.start > -INF() and cell.ends < INF() then
        time = fmtRange(cell.start, cell.ends)
        if rating <> "" then time = time + " · " + rating
    end if
    return { title: cell.title, ep: ep, time: time, plot: plot }
end function

' ---- where the highlight and the window may be -----------------------------------

function minWin() as integer
    return floorHalf(now())
end function

function maxWin() as integer
    return maxI(minWin(), floorHalf(m.S.dataEnd - 1) - (m.lay.slots - 1) * HALF())
end function

sub clampState()
    S = m.S
    n = S.channels.Count()
    if n = 0 then return
    S.winStart = clampI(S.winStart, minWin(), maxWin())
    S.focusTime = clampI(S.focusTime, S.winStart, S.winStart + m.lay.span - 1)
    S.focusCh = clampI(S.focusCh, 0, n - 1)
    if S.focusCh < S.rowTop then S.rowTop = S.focusCh
    if S.focusCh >= S.rowTop + m.lay.rows then S.rowTop = S.focusCh - m.lay.rows + 1
    S.rowTop = clampI(S.rowTop, 0, maxI(0, n - m.lay.rows))
end sub

function focusChannel() as object
    return m.S.channels[m.S.focusCh]
end function

function focusCell() as object
    return cellAt(focusChannel(), m.S.focusTime)
end function

' ---- drawing the guide -------------------------------------------------------------

sub render()
    if m.S.channels.Count() = 0 then return
    clampState()
    renderGrid()
    renderInfo()
    if m.S.mode = "details" then renderDetails()
end sub

' One grid cell in the theme's shape, and a label unless it is too narrow
' (30 px). kind as in cellBox.
sub drawCell(x as integer, y as integer, w as integer, text as string, kind as string, bg as string, fg as string, withLabel as boolean)
    th = m.T
    r = cellBox(m.gridCells, px(x), px(y), px(x + w) - px(x), px(27), kind, bg)
    if not withLabel then return
    fsize = th.cellSize
    if kind = "chan" or kind = "selchan" then fsize = th.chanSize
    if kind = "clock" then fsize = th.clockSize
    pad = 7
    if fsize > 16 then pad = 5
    l = label(r, px(pad), 0, px(w) - px(2 * pad), px(27), fsize * KK(), true, fg)
    if th.centerBar and (kind = "clock" or kind = "bar") then l.horizAlign = "center"
    l.text = cellCase(text, kind = "chan" or kind = "selchan")
    if kind <> "sel" and kind <> "selchan" then addShadow(l)
end sub

sub renderGrid()
    lay = m.lay
    S = m.S
    th = m.T
    t0 = S.winStart
    t1 = t0 + lay.span
    tnow = now()
    m.gridCells.removeChildrenIndex(m.gridCells.getChildCount(), 0)

    drawCell(0, 2, lay.chanW, fmtDay(tnow) + " " + fmtTime(tnow), "clock", col("clockfill"), col("clocktext"), true)
    for i = 0 to lay.slots - 1
        a = t0 + i * HALF()
        lx = gx(a)
        rx = gx(a + HALF())
        w = rx - lx
        if i < lay.slots - 1 then w = w - 2
        drawCell(lx, 2, w, fmtTime(a), "bar", col("timebar"), col("slottext"), true)
    end for

    for r = 0 to lay.rows - 1
        ci = S.rowTop + r
        if ci >= S.channels.Count() then exit for
        ch = S.channels[ci]
        y = 2 + lay.row * (r + 1)
        focused = ci = S.focusCh and not S.cog
        ckind = "chan"
        bg = col("channel")
        fg = col("chantext")
        if focused then
            ckind = "selchan"
            bg = col("yellow")
            fg = col("seltext")
        else if ci = S.tuned then
            fg = col("accent")
        end if
        name = ch.num + " " + ch.name
        if ci = S.tuned then
            ' The channel being watched: a small flat triangle before its name.
            rr = cellBox(m.gridCells, 0, px(y), px(lay.chanW), px(27), ckind, bg)
            tri = CreateObject("roSGNode", "Poster")
            tri.uri = "pkg:/images/tri.png"
            tri.blendColor = col("yellow")
            if focused then tri.blendColor = col("seltext")
            tri.translation = [px(7), px(8.5)]
            tri.width = px(8)
            tri.height = px(10)
            rr.appendChild(tri)
            l = label(rr, px(20), 0, px(lay.chanW - 25), px(27), th.chanSize * KK(), true, fg)
            l.text = cellCase(name, true)
            if not focused then addShadow(l)
        else
            drawCell(0, y, lay.chanW, name, ckind, bg, fg, true)
        end if

        t = t0
        while t < t1
            c = cellAt(ch, t)
            a = maxI(c.start, t0)
            b = minI(c.ends, t1)
            lx = gx(a)
            w = gx(b) - lx
            if b < t1 then w = w - 2
            if w >= 2 then
                sel = focused and S.focusTime >= c.start and S.focusTime < c.ends
                skind = "show"
                cbg = col("program")
                cfg = col("text")
                if c.gap = true then cfg = col("soft")
                if sel then
                    skind = "sel"
                    cbg = col("yellow")
                    cfg = col("seltext")
                end if
                drawCell(lx, y, w, cellLabel(c), skind, cbg, cfg, w >= 30)
            end if
            if not (b > t) then exit while
            t = b
        end while
    end for

    if tnow >= t0 and tnow < t1 then
        rect(m.gridCells, px(minI(gx(tnow), lay.W - 2)), px(2), px(2), px(27), col("yellow"))
    end if

    if S.cog or S.mode = "settings" or S.mode = "themes" then
        m.cog.blendColor = col("accent")
    else
        m.cog.blendColor = col("soft")
    end if
end sub

' Time to design x.
function gx(t as integer) as integer
    return m.lay.timeX + Int((t - m.S.winStart) / m.lay.span * m.lay.timeW + 0.5)
end function

sub renderInfo()
    ch = focusChannel()
    d = describe(focusCell())
    m.infoCh.text = "Ch " + ch.num + " · " + ch.name
    m.infoTitle.text = cellCase(d.title, false)
    m.infoEp.text = d.ep
    m.infoTime.text = d.time
    plot = d.plot
    if m.S.mode = "details" then plot = ""
    renderInfoLayout(d.ep, d.time, plot)
end sub

' ---- show details (over the grid) ----------------------------------------------

sub openDetails()
    if focusCell().gap = true then return
    m.S.mode = "details"
    m.S.detBtn = 0
    m.detScroll = 0
    m.details.visible = true
    render()
end sub

sub closeDetails()
    m.S.mode = "guide"
    m.details.visible = false
    render()
end sub

sub renderDetails()
    lay = m.lay
    g = m.details
    g.removeChildrenIndex(g.getChildCount(), 0)
    top = lay.gridTop
    rect(g, 0, px(top), 1920, 1080 - px(top), col("navy"))
    rect(g, 0, px(top), 1920, px(2), col("gap"))

    c = focusCell()
    one = invalid
    if c.items.Count() = 1 then one = c.items[0]
    first = invalid
    if c.items.Count() > 0 then first = c.items[0]

    x = 8
    innerTop = top + 2 + 10
    innerH = lay.H - innerTop - 8
    if first <> invalid and first.icon <> "" then
        poster = CreateObject("roSGNode", "Poster")
        poster.uri = first.icon
        poster.loadDisplayMode = "scaleToFit"
        poster.translation = [px(x), px(innerTop)]
        poster.width = px(Int(lay.W * 0.34) - 8)
        poster.height = px(innerH)
        poster.loadWidth = poster.width
        poster.loadHeight = poster.height
        g.appendChild(poster)
        ' Like the viewer, the poster hugs the top left of its pbox.
        poster.loadingBitmapUri = ""
        x = Int(lay.W * 0.34) + 12
    end if
    w = lay.W - 8 - x

    meta = []
    if one <> invalid then
        for each part in [one.ep, one.year, one.rating, one.genres]
            if part <> "" then meta.Push(part)
        end for
    else if first <> invalid then
        meta.Push(c.items.Count().ToStr() + " shorts")
        if first.rating <> "" then meta.Push(first.rating)
    end if
    ml = label(g, px(x), px(innerTop), px(w), px(20), 16 * KK(), true, col("accent"))
    ml.text = meta.Join(" · ")
    addShadow(ml)

    body = ""
    if one <> invalid then
        body = one.desc
        if body = "" then body = "No description."
    else
        parts = []
        for each p in c.items
            name = p.sub
            if name = "" then name = p.title
            parts.Push(fmtTime(p.start) + "  " + name + Chr(10) + p.desc)
        end for
        body = parts.Join(Chr(10) + Chr(10))
    end if
    textTop = innerTop + 20 + 6
    btnTop = lay.H - 8 - 31
    clip = CreateObject("roSGNode", "Group")
    clip.clippingRect = [px(x), px(textTop), px(w), px(btnTop - 6 - textTop)]
    g.appendChild(clip)
    tl = CreateObject("roSGNode", "Label")
    tl.font = font(16 * KK(), false)
    tl.color = col("soft")
    tl.wrap = true
    tl.lineSpacing = px(21) - Int(16 * KK() * 1.2)
    tl.width = px(w)
    tl.translation = [px(x), px(textTop) - m.detScroll]
    tl.text = body
    clip.appendChild(tl)
    addShadow(tl)

    ' Buttons: Watch now, Back (2 px black lines between).
    labels = ["Watch now", "Back"]
    bx = x
    widths = [96, 54]
    if m.T.btnSize > 16 then widths = [118, 62]
    rect(g, px(bx), px(btnTop), px(2 + widths[0] + 2 + widths[1] + 2), px(31), col("lines"))
    for i = 0 to 1
        bkind = "chan"
        bg = col("channel")
        fg = col("text")
        if i = m.S.detBtn then
            bkind = "sel"
            bg = col("yellow")
            fg = col("seltext")
        end if
        r = cellBox(g, px(bx + 2), px(btnTop + 2), px(widths[i]), px(27), bkind, bg)
        l = label(r, 0, 0, px(widths[i]), px(27), m.T.btnSize * KK(), true, fg)
        l.horizAlign = "center"
        l.text = cellCase(labels[i], false)
        if bkind <> "sel" then addShadow(l)
        bx = bx + 2 + widths[i]
    end for
end sub

' ---- settings (over the grid) ----------------------------------------------------

function settingRows() as object
    rows = []
    rows.Push({ id: "theme", label: "Theme", value: m.T.label, help: m.T.help + " OK shows them all." })
    if m.S.hasHd then
        q = "Standard"
        help = "The 4:3 picture made for the old TV. Lightest on the connection."
        if m.quality = "hd" then
            q = "HD"
            help = "The same channels in widescreen 1080p, for modern screens. Needs a faster connection."
        end if
        rows.Push({ id: "quality", label: "Quality", value: q, help: help })
    end if
    rows.Push({ id: "server", label: "TV server", value: m.server, help: "Where ErsatzTV answers on your network. OK to change it." })
    return rows
end function

sub openSettings()
    m.S.cog = false
    m.S.setRow = 0
    m.S.mode = "settings"
    m.settings.visible = true
    renderSettings()
    render()
end sub

sub closeSettings()
    m.S.mode = "guide"
    m.settings.visible = false
    render()
end sub

sub renderSettings()
    lay = m.lay
    g = m.settings
    g.removeChildrenIndex(g.getChildCount(), 0)
    top = lay.gridTop
    rect(g, 0, px(top), 1920, 1080 - px(top), col("navy"))
    rect(g, 0, px(top), 1920, px(2), col("gap"))
    y = top + 2 + 10
    t = label(g, px(8), px(y), px(400), px(20), 16 * KK(), true, col("accent"))
    t.text = "Settings for this device"
    addShadow(t)
    y = y + 20 + 8

    rows = settingRows()
    labelW = 120
    valueW = 260
    n = rows.Count()
    rect(g, px(8), px(y), px(2 + labelW + 2 + valueW + 2), px(2 + n * 29), col("lines"))
    for i = 0 to n - 1
        sel = i = m.S.setRow
        lb = col("channel")
        vb = col("program")
        fg = col("text")
        k1 = "chan"
        k2 = "show"
        if sel then
            lb = col("yellow")
            vb = col("yellow")
            fg = col("seltext")
            k1 = "selchan"
            k2 = "sel"
        end if
        ry = y + 2 + i * 29
        r1 = cellBox(g, px(10), px(ry), px(labelW), px(27), k1, lb)
        l1 = label(r1, px(10), 0, px(labelW - 20), px(27), m.T.btnSize * KK(), true, fg)
        l1.text = cellCase(rows[i].label, false)
        if not sel then addShadow(l1)
        r2 = cellBox(g, px(10 + labelW + 2), px(ry), px(valueW), px(27), k2, vb)
        l2 = label(r2, px(10), 0, px(valueW - 20), px(27), m.T.btnSize * KK(), true, fg)
        l2.text = cellCase(rows[i].value, false)
        if not sel then addShadow(l2)
    end for
    y = y + 2 + n * 29 + 8

    help = "Remote: OK watch · Play/Pause show details · Replay settings · Back picture."
    if m.S.setRow < n then help = rows[m.S.setRow].help
    hl = CreateObject("roSGNode", "Label")
    hl.font = font(15 * KK(), false)
    hl.color = col("soft")
    hl.wrap = true
    hl.translation = [px(8), px(y)]
    hl.width = px(lay.W - 16)
    hl.text = help
    g.appendChild(hl)
    addShadow(hl)

    ' Done button, bottom left.
    by = lay.H - 8 - 31
    doneW = 54
    if m.T.btnSize > 16 then doneW = 66
    rect(g, px(8), px(by), px(2 + doneW + 2), px(31), col("lines"))
    bkind = "chan"
    bg = col("channel")
    fg = col("text")
    if m.S.setRow = n then
        bkind = "sel"
        bg = col("yellow")
        fg = col("seltext")
    end if
    r = cellBox(g, px(10), px(by + 2), px(doneW), px(27), bkind, bg)
    l = label(r, 0, 0, px(doneW), px(27), m.T.btnSize * KK(), true, fg)
    l.horizAlign = "center"
    l.text = cellCase("Done", false)
    if bkind <> "sel" then addShadow(l)
end sub

sub changeSetting()
    rows = settingRows()
    if m.S.setRow >= rows.Count() then
        closeSettings()
        return
    end if
    id = rows[m.S.setRow].id
    if id = "theme" then
        openThemes()
        return
    else if id = "quality" then
        if m.quality = "hd" then
            m.quality = "sd"
        else
            m.quality = "hd"
        end if
        regWrite("quality", m.quality)
        ' Switch the channel being watched to its other stream right away.
        if m.S.tuned >= 0 then playStream()
    else if id = "server" then
        askServer(m.server)
    end if
    renderSettings()
end sub

' ---- theme picker (over the grid, from the Theme row in settings) -----------------
' Every theme as a small tile in its own colours and face, three across.

sub openThemes()
    ids = themeIds()
    m.S.tpIndex = 0
    for i = 0 to ids.Count() - 1
        if ids[i] = m.theme then m.S.tpIndex = i
    end for
    m.S.mode = "themes"
    m.settings.visible = false
    m.picker.visible = true
    renderPicker()
    renderGrid()
end sub

sub closeThemes()
    m.S.mode = "settings"
    m.picker.visible = false
    m.settings.visible = true
    renderSettings()
end sub

sub renderPicker()
    lay = m.lay
    g = m.picker
    g.removeChildrenIndex(g.getChildCount(), 0)
    top = lay.gridTop
    rect(g, 0, px(top), 1920, 1080 - px(top), col("navy"))
    rect(g, 0, px(top), 1920, px(2), col("gap"))
    hd = label(g, px(8), px(top + 10), px(400), px(20), 16 * KK(), true, col("accent"))
    hd.text = "Pick a theme"
    addShadow(hd)

    ids = themeIds()
    all = themeTable()
    tileW = 275
    tileH = 64
    for i = 0 to ids.Count() - 1
        th = all[ids[i]]
        c = th.colors
        tx = 8 + (i mod 3) * (tileW + 6)
        ty = top + 36 + Int(i / 3) * (tileH + 6)
        if i = m.S.tpIndex then rect(g, px(tx), px(ty), px(tileW), px(tileH), col("yellow"))
        tile = rect(g, px(tx + 3), px(ty + 3), px(tileW - 6), px(tileH - 6), c.navy)
        nl = CreateObject("roSGNode", "Label")
        nl.translation = [px(6), px(2)]
        nl.width = px(tileW - 6 - 70)
        nl.height = px(18)
        nl.vertAlign = "center"
        nl.font = faceFont(th.display, 14 * KK())
        nl.color = c.white
        nl.text = th.label
        if th.upper then nl.text = UCase(th.label)
        tile.appendChild(nl)
        if ids[i] = m.theme then
            badge = rect(tile, px(tileW - 6 - 50), px(4), px(46), px(15), c.yellow)
            bl = CreateObject("roSGNode", "Label")
            bl.width = px(46)
            bl.height = px(15)
            bl.horizAlign = "center"
            bl.vertAlign = "center"
            bl.font = faceFont(th.bold, 11 * KK())
            bl.color = c.seltext
            bl.text = "In use"
            badge.appendChild(bl)
        end if
        ' Three small rows: the time bar, a row with the highlight, a plain row.
        inner = tileW - 6 - 12
        u = (inner - 4) / 8
        fills = [[c.clockfill, c.timebar, c.timebar], [c.channel, c.yellow, c.program], [c.channel, c.program, c.program]]
        for r = 0 to 2
            ry = 24 + r * 11
            rect(tile, px(6), px(ry), px(2 * u), px(9), fills[r][0])
            rect(tile, px(6 + 2 * u + 2), px(ry), px(3 * u), px(9), fills[r][1])
            rect(tile, px(6 + 5 * u + 4), px(ry), px(3 * u), px(9), fills[r][2])
        end for
    end for

    hl = label(g, px(8), px(lay.H - 24), px(lay.W - 16), px(18), 13 * KK(), false, col("soft"))
    hl.text = all[ids[m.S.tpIndex]].help
    addShadow(hl)
end sub

sub moveTheme(delta as integer)
    target = m.S.tpIndex + delta
    if target < 0 or target > themeIds().Count() - 1 then return
    m.S.tpIndex = target
    renderPicker()
end sub

' Reskin at once, back in settings, and show the new theme's splash so the
' change is seen.
sub pickTheme()
    applyTheme(themeIds()[m.S.tpIndex])
    regWrite("theme", m.theme)
    m.S.mode = "settings"
    rebuildStage()
    showSplash(2)
end sub

' ---- watching ----------------------------------------------------------------

function playingHd() as boolean
    if m.S.tuned < 0 then return false
    return m.quality = "hd" and m.S.hasHd and m.S.channels[m.S.tuned].hd <> ""
end function

sub tune(ci as integer)
    m.S.tuned = ci
    regWrite("channel", m.S.channels[ci].num)
    m.previewMsg.visible = false
    playStream()
end sub

sub playStream()
    ch = m.S.channels[m.S.tuned]
    num = ch.num
    if playingHd() then num = ch.hd
    content = CreateObject("roSGNode", "ContentNode")
    content.url = m.server + "/iptv/channel/" + num + ".m3u8?mode=segmenter"
    content.streamFormat = "hls"
    content.title = ch.name
    content.live = true
    m.video.content = content
    m.video.mute = m.S.muted
    m.video.control = "play"
    m.S.playState = "tuning"
    m.tuning.text = "Tuning to " + ch.num + " " + ch.name + "…"
    m.tuning.visible = true
    placeVideo()
end sub

sub onVideoState()
    st = m.video.state
    if st = "playing" then
        m.S.playState = "playing"
        m.tuning.visible = false
    else if st = "error" or st = "finished" then
        m.S.playState = "error"
        m.tuning.text = "Channel unavailable, retrying…"
        m.tuning.visible = true
        m.playRetry.control = "start"
    end if
end sub

sub retryPlay()
    if m.S.tuned >= 0 and m.S.playState = "error" then playStream()
end sub

' Select: straight into the full picture, tuning first if needed.
sub watch(ci as integer)
    if m.S.tuned <> ci or m.S.playState = "error" or m.S.playState = "idle" then tune(ci)
    setMode("full")
    m.S.banBtn = 0
    showBanner()
end sub

sub stepChannel(delta as integer)
    n = m.S.channels.Count()
    if n = 0 then return
    at = m.S.tuned
    if at < 0 then at = m.S.focusCh
    nxt = ((at + delta) mod n + n) mod n
    m.S.focusCh = nxt
    tune(nxt)
    render()
    showBanner()
end sub

' Back to the guide, highlight on what is playing now.
sub openGuide()
    if m.S.tuned >= 0 then
        m.S.focusCh = m.S.tuned
        m.S.focusTime = now()
        m.S.winStart = minWin()
    end if
    setMode("guide")
end sub

sub setMode(mode as string)
    m.S.mode = mode
    m.stage.visible = mode <> "full"
    m.details.visible = mode = "details"
    m.settings.visible = mode = "settings"
    m.picker.visible = mode = "themes"
    if mode <> "full" then hideBanner()
    placeVideo()
    render()
end sub

sub toggleMute()
    m.S.muted = not m.S.muted
    m.video.mute = m.S.muted
    if m.S.muted then
        showOsd("Sound is off")
    else
        showOsd("Sound is on")
    end if
    if m.banner.visible then fillBanner()
end sub

' ---- channel bar (locked to the bottom of the picture) -----------------------------

sub showBanner()
    if m.S.mode <> "full" or m.S.tuned < 0 then return
    fillBanner()
    m.banner.visible = true
    t = m.top.findNode("bannerTimer")
    t.control = "stop"
    t.control = "start"
end sub

sub hideBanner()
    m.banner.visible = false
end sub

' The viewer's bar at b = 1.5 (its size for a TV across the room).
sub fillBanner()
    g = m.banner
    g.removeChildrenIndex(g.getChildCount(), 0)
    b = 1.5
    pbox = pictureBox()
    ch = m.S.channels[m.S.tuned]
    tnow = now()
    p = programmeAt(ch, tnow)

    padX = Int(20 * b)
    hBody = Int((14 + 22 + 15) * 1.25 * b) + Int(4 * b)
    hBar = Int(2 * b) + Int(4 * b) + Int(12 * b) + hBody + Int(14 * b)
    top = 1080 - hBar
    rect(g, pbox.x, top, pbox.w, Int(2 * b), col("yellow"))
    rect(g, pbox.x, top + Int(2 * b), pbox.w, hBar - Int(2 * b), col("navy"))
    barY = top + Int(2 * b)
    rect(g, pbox.x, barY, pbox.w, Int(4 * b), col("program"))
    if p <> invalid and p.ends > p.start then
        frac = (tnow - p.start) / (p.ends - p.start)
        if frac < 0 then frac = 0
        if frac > 1 then frac = 1
        rect(g, pbox.x, barY, Int(pbox.w * frac), Int(4 * b), col("yellow"))
    end if

    y = barY + Int(4 * b) + Int(12 * b)
    x = pbox.x + padX
    btnW = [Int(60 * b), Int(58 * b), Int(58 * b), Int(66 * b)]
    if m.S.muted then btnW[3] = Int(80 * b)
    if m.T.btnSize > 16 then
        btnW = [Int(72 * b), Int(66 * b), Int(66 * b), Int(72 * b)]
        if m.S.muted then btnW[3] = Int(96 * b)
    end if
    btnTotal = Int(2 * b)
    for each w in btnW
        btnTotal = btnTotal + w + Int(2 * b)
    end for
    infoW = pbox.w - 2 * padX - btnTotal - Int(24 * b)

    title = "No information"
    sub1 = ""
    if p <> invalid then
        title = p.title
        parts = []
        if p.sub <> "" then
            parts.Push(Chr(34) + p.sub + Chr(34))
        else if p.movie and p.year <> "" then
            parts.Push(p.year)
        end if
        t = fmtRange(p.start, p.ends)
        if p.rating <> "" then t = t + " · " + p.rating
        parts.Push(t)
        sub1 = parts.Join(" · ")
    end if
    l = label(g, x, y, infoW, Int(14 * 1.25 * b), 14 * b, true, col("accent"))
    l.text = "Ch " + ch.num + " · " + ch.name
    addShadow(l)
    l = label(g, x, y + Int(14 * 1.25 * b) + Int(2 * b), infoW, Int(22 * 1.25 * b), 22 * b, true, col("white"))
    l.font = displayFont(22 * b)
    l.text = cellCase(title, false)
    addShadow(l)
    l = label(g, x, y + Int(36 * 1.25 * b) + Int(4 * b), infoW, Int(15 * 1.25 * b), 15 * b, true, col("soft"))
    l.text = sub1
    addShadow(l)

    ' Right column: clock above the buttons.
    rightX = pbox.x + pbox.w - padX
    l = label(g, rightX - Int(200 * b), y, Int(200 * b), Int(15 * 1.25 * b), 15 * b, true, col("white"))
    l.horizAlign = "right"
    l.text = fmtTime(tnow)
    addShadow(l)
    names = ["Guide", "Ch −", "Ch +", "Mute"]
    if m.S.muted then names[3] = "Unmute"
    bh = Int(28 * b) + Int(4 * b)
    by = y + Int(36 * 1.25 * b) + Int(4 * b) + Int(15 * 1.25 * b) - bh
    bx = rightX - btnTotal
    rect(g, bx, by, btnTotal, bh, col("lines"))
    bx = bx + Int(2 * b)
    for i = 0 to 3
        bkind = "chan"
        bg = col("channel")
        fg = col("text")
        if i = m.S.banBtn then
            bkind = "sel"
            bg = col("yellow")
            fg = col("seltext")
        end if
        r = cellBox(g, bx, by + Int(2 * b), btnW[i], Int(28 * b), bkind, bg)
        bl = label(r, 0, 0, btnW[i], Int(28 * b), 15 * b, true, fg)
        bl.horizAlign = "center"
        bl.text = cellCase(names[i], false)
        if bkind <> "sel" then addShadow(bl)
        bx = bx + btnW[i] + Int(2 * b)
    end for
end sub

sub pressBannerButton()
    i = m.S.banBtn
    if i = 0 then
        openGuide()
    else if i = 1 then
        stepChannel(-1)
    else if i = 2 then
        stepChannel(1)
    else
        toggleMute()
        showBanner()
    end if
end sub

' ---- short messages (top right of the picture) -------------------------------------

sub showOsd(text as string)
    g = m.osd
    g.removeChildrenIndex(g.getChildCount(), 0)
    b = 1.5
    pbox = pictureBox()
    w = Int((Len(text) * 11 + 24) * b)
    h = Int(36 * b)
    x = pbox.x + pbox.w - Int(24 * b) - w
    y = pbox.y + Int(24 * b)
    rect(g, x, y, w, h, col("yellow"))
    rect(g, x + Int(2 * b), y + Int(2 * b), w - Int(4 * b), h - Int(4 * b), col("navy"))
    l = label(g, x + Int(12 * b), y, w - Int(24 * b), h, 21 * b, true, col("accent"))
    l.text = text
    g.visible = true
    t = m.top.findNode("osdTimer")
    t.control = "stop"
    t.control = "start"
end sub

sub hideOsd()
    m.osd.visible = false
end sub

sub onTick()
    if m.S.mode <> "full" then render()
    if m.banner.visible then fillBanner()
end sub

' ---- moving around the guide ------------------------------------------------------

' wrap: a press at either end of the list goes round to the other end (a
' held key does not: it stops at the end).
sub moveRow(delta as integer, wrap as boolean)
    lastCh = m.S.channels.Count() - 1
    target = m.S.focusCh + delta
    if wrap and delta > 0 and m.S.focusCh = lastCh then
        target = 0
    else if wrap and delta < 0 and m.S.focusCh = 0 then
        target = lastCh
    end if
    m.S.focusCh = clampI(target, 0, lastCh)
    render()
end sub

' Holding Up or Down in the guide: the remote sends one press and one
' release, so a timer does the repeating, faster the longer the key is held
' (about 8 rows a second, then 16, then 25).
sub startHold(dir as integer)
    m.holdDir = dir
    m.holdTicks = 0
    m.holdTimer.control = "stop"
    m.holdTimer.control = "start"
end sub

sub stopHold()
    m.holdDir = 0
    m.holdTimer.control = "stop"
end sub

sub onHoldTick()
    if m.holdDir = 0 or m.S.mode <> "guide" or m.S.cog then
        stopHold()
        return
    end if
    m.holdTicks = m.holdTicks + 1
    if m.holdTicks < 4 then return        ' a short press is one row
    rowsNow = 1
    if m.holdTicks > 12 then rowsNow = 2
    if m.holdTicks > 24 then rowsNow = 3
    moveRow(m.holdDir * rowsNow, false)
end sub

sub moveTime(dir as integer)
    S = m.S
    c = focusCell()
    mn = minWin()
    if dir > 0 then
        if c.ends >= INF() or c.ends >= S.dataEnd then return
        S.focusTime = c.ends
        while S.focusTime >= S.winStart + m.lay.span
            S.winStart = S.winStart + HALF()
        end while
    else if c.start < S.winStart and S.winStart > mn then
        ' The show began to the left of the window: bring its start into view.
        S.winStart = maxI(mn, floorHalf(c.start))
        S.focusTime = maxI(c.start, S.winStart)
    else if c.start > mn then
        prev = cellAt(focusChannel(), c.start - 1)
        S.focusTime = maxI(prev.start, mn)
        S.winStart = minI(S.winStart, maxI(mn, floorHalf(S.focusTime)))
    end if
    render()
end sub

' ---- remote -------------------------------------------------------------------------

function onKeyEvent(key as string, press as boolean) as boolean
    if m.holdDir <> 0 then stopHold()      ' any release or new press ends a held Up / Down
    if not press then return false
    if m.splash <> invalid and m.splash.visible then return true   ' nothing moves under the splash
    S = m.S
    if S.channels.Count() = 0 then
        if key = "replay" or key = "options" then
            askServer(m.server)
            return true
        end if
        return false
    end if

    if S.mode = "settings" then
        n = settingRows().Count()
        if key = "up" then
            S.setRow = maxI(0, S.setRow - 1)
            renderSettings()
        else if key = "down" then
            S.setRow = minI(n, S.setRow + 1)
            renderSettings()
        else if key = "left" or key = "right" or key = "OK" then
            changeSetting()
        else if key = "back" or key = "replay" or key = "options" then
            closeSettings()
        end if
        return true
    end if

    if S.mode = "themes" then
        if key = "up" then
            moveTheme(-3)
        else if key = "down" then
            moveTheme(3)
        else if key = "left" then
            moveTheme(-1)
        else if key = "right" then
            moveTheme(1)
        else if key = "OK" then
            pickTheme()
        else if key = "back" or key = "replay" or key = "options" then
            closeThemes()
        end if
        return true
    end if

    if S.mode = "details" then
        if key = "up" then
            m.detScroll = maxI(0, m.detScroll - px(42))
            renderDetails()
        else if key = "down" then
            m.detScroll = m.detScroll + px(42)
            renderDetails()
        else if key = "left" or key = "right" then
            S.detBtn = 1 - S.detBtn
            renderDetails()
        else if key = "OK" then
            if S.detBtn = 0 then
                ci = S.focusCh
                closeDetails()
                watch(ci)
            else
                closeDetails()
            end if
        else if key = "back" or key = "play" then
            closeDetails()
        end if
        return true
    end if

    if S.mode = "guide" then
        if S.cog then
            if key = "OK" then
                openSettings()
            else if key = "down" or key = "back" then
                S.cog = false
                render()
            else if key = "up" then
                ' Up again from the cog: round to the last channel.
                S.cog = false
                moveRow(-1, true)
            end if
            return true
        end if
        if key = "up" then
            if S.focusCh = 0 then
                S.cog = true
                render()
            else
                moveRow(-1, false)
                startHold(-1)
            end if
        else if key = "down" then
            moveRow(1, true)
            startHold(1)
        else if key = "left" then
            moveTime(-1)
        else if key = "right" then
            moveTime(1)
        else if key = "rewind" then
            moveRow(-m.lay.rows, true)
        else if key = "fastforward" then
            moveRow(m.lay.rows, true)
        else if key = "OK" then
            watch(S.focusCh)
        else if key = "play" then
            openDetails()
        else if key = "replay" or key = "options" then
            openSettings()
        else if key = "back" then
            if S.tuned >= 0 then
                setMode("full")
                showBanner()
                return true
            end if
            return false
        end if
        return true
    end if

    ' Watching.
    if key = "up" or key = "fastforward" then
        stepChannel(1)
    else if key = "down" or key = "rewind" then
        stepChannel(-1)
    else if key = "back" then
        openGuide()
    else if key = "OK" then
        if m.banner.visible then
            pressBannerButton()
        else
            showBanner()
        end if
    else if key = "left" or key = "right" then
        if m.banner.visible then
            if key = "left" then
                S.banBtn = (S.banBtn + 3) mod 4
            else
                S.banBtn = (S.banBtn + 1) mod 4
            end if
        end if
        showBanner()
    else if key = "play" then
        toggleMute()
    else
        return false
    end if
    return true
end function
