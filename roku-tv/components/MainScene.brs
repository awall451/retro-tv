' Retro TV main scene.
'
' Remote:  Up / Down        channel up / down
'          OK               show or hide the channel bar
'          * (options)      switch between Standard and HD
'          Back             leave the app
'
' Settings live in the device registry (section "RetroTV"):
'   server   "http://<server-ip>:8409", asked for on first start
'   channel  last channel watched
'   quality  "sd" or "hd"

sub init()
    m.video = m.top.findNode("video")
    m.bar = m.top.findNode("bar")
    m.barCh = m.top.findNode("barCh")
    m.barTitle = m.top.findNode("barTitle")
    m.barHint = m.top.findNode("barHint")
    m.barClock = m.top.findNode("barClock")
    m.barQuality = m.top.findNode("barQuality")
    m.msgBox = m.top.findNode("msgBox")
    m.msgText = m.top.findNode("msgText")
    m.barTimer = m.top.findNode("barTimer")
    m.barTimer.observeField("fire", "hideBar")
    m.video.observeField("state", "onVideoState")

    m.reg = CreateObject("roRegistrySection", "RetroTV")
    m.channels = []      ' the channels in the guide (HD twins left out)
    m.hdNums = {}        ' channel number -> true when it has an HD twin
    m.at = 0
    m.failed = false
    m.playingHd = false
    m.server = ""
    m.quality = regRead("quality", "sd")

    m.top.setFocus(true)
    server = regRead("server", "")
    if server = "" then
        askServer("")
    else
        loadChannels(server)
    end if
end sub

' ---- settings -------------------------------------------------------------

function regRead(key as string, fallback as string) as string
    if m.reg.Exists(key) then return m.reg.Read(key)
    return fallback
end function

sub regWrite(key as string, value as string)
    m.reg.Write(key, value)
    m.reg.Flush()
end sub

' First start (or after a failed load): ask for the ErsatzTV address.
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
    loadChannels(text)
end sub

' ---- channel list -----------------------------------------------------------

sub loadChannels(server as string)
    m.server = server
    showMsg("Loading channels from " + server + " ...")
    m.task = CreateObject("roSGNode", "ChannelsTask")
    m.task.server = server
    m.task.observeField("channels", "onChannels")
    m.task.observeField("error", "onChannelsError")
    m.task.control = "run"
end sub

sub onChannelsError()
    showMsg(m.task.error + Chr(10) + "Press OK to change the address.")
    m.failed = true
end sub

sub onChannels()
    m.channels = []
    m.hdNums = {}
    for each c in m.task.channels
        if c.group = "HD" then
            m.hdNums[(c.n - 100).ToStr()] = true
        else
            m.channels.Push(c)
        end if
    end for
    if m.channels.Count() = 0 then
        showMsg("The server has no channels." + Chr(10) + "Press OK to change the address.")
        m.failed = true
        return
    end if
    m.failed = false
    hideMsg()

    last = regRead("channel", m.channels[0].num)
    m.at = 0
    for i = 0 to m.channels.Count() - 1
        if m.channels[i].num = last then m.at = i
    end for
    tune()
end sub

' ---- playing ----------------------------------------------------------------

sub tune()
    ch = m.channels[m.at]
    num = ch.num
    hd = m.quality = "hd" and m.hdNums.DoesExist(num)
    if hd then num = (ch.n + 100).ToStr()

    content = CreateObject("roSGNode", "ContentNode")
    content.url = m.server + "/iptv/channel/" + num + ".m3u8?mode=segmenter"
    content.streamFormat = "hls"
    content.title = ch.name
    content.live = true
    m.video.content = content
    m.video.control = "play"

    regWrite("channel", ch.num)
    m.playingHd = hd
    showBar()
end sub

sub step(delta as integer)
    n = m.channels.Count()
    if n = 0 then return
    m.at = ((m.at + delta) mod n + n) mod n
    tune()
end sub

sub onVideoState()
    state = m.video.state
    if state = "error" then
        showMsg("This channel did not start (" + m.video.errorMsg + ")." + Chr(10) + "Try another channel.")
    else if state = "playing" then
        hideMsg()
    end if
end sub

' ---- channel bar ------------------------------------------------------------

sub showBar()
    if m.channels.Count() = 0 then return
    ch = m.channels[m.at]
    m.barCh.text = "Ch " + ch.num
    m.barTitle.text = ch.name
    m.barHint.text = "Up / Down  change channel     OK  hide     *  Standard / HD"
    m.barClock.text = clockText()
    if m.playingHd then
        m.barQuality.text = "HD"
    else if m.quality = "hd" then
        m.barQuality.text = "Standard (no HD copy)"
    else
        m.barQuality.text = "Standard"
    end if
    m.bar.visible = true
    m.barTimer.control = "stop"
    m.barTimer.control = "start"
end sub

sub hideBar()
    m.bar.visible = false
end sub

function clockText() as string
    now = CreateObject("roDateTime")
    now.ToLocalTime()
    h = now.GetHours()
    suffix = "AM"
    if h >= 12 then suffix = "PM"
    h = h mod 12
    if h = 0 then h = 12
    mins = now.GetMinutes().ToStr()
    if Len(mins) = 1 then mins = "0" + mins
    return h.ToStr() + ":" + mins + " " + suffix
end function

' ---- messages ---------------------------------------------------------------

sub showMsg(text as string)
    m.msgText.text = text
    m.msgBox.visible = true
end sub

sub hideMsg()
    m.msgBox.visible = false
end sub

' ---- remote -----------------------------------------------------------------

function onKeyEvent(key as string, press as boolean) as boolean
    if not press then return false
    if m.failed then
        if key = "OK" then
            askServer(m.server)
            return true
        end if
        return false
    end if
    if key = "up" or key = "fastforward" then
        step(1)
        return true
    else if key = "down" or key = "rewind" then
        step(-1)
        return true
    else if key = "OK" then
        if m.bar.visible then
            hideBar()
        else
            showBar()
        end if
        return true
    else if key = "options" then
        if m.quality = "hd" then
            m.quality = "sd"
        else
            m.quality = "hd"
        end if
        regWrite("quality", m.quality)
        tune()
        return true
    end if
    return false
end function
