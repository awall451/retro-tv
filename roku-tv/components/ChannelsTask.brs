sub init()
    m.top.functionName = "fetch"
end sub

' Reads <server>/iptv/channels.m3u. Each channel is an #EXTINF line with
' channel-number="N", group-title="G" and the name after the last comma.
sub fetch()
    http = CreateObject("roUrlTransfer")
    http.SetUrl(m.top.server + "/iptv/channels.m3u")
    http.EnableEncodings(true)
    port = CreateObject("roMessagePort")
    http.SetMessagePort(port)
    if not http.AsyncGetToString() then
        m.top.error = "Could not start the request"
        return
    end if
    msg = wait(10000, port)
    if msg = invalid then
        http.AsyncCancel()
        m.top.error = "No answer from " + m.top.server
        return
    end if
    if msg.GetResponseCode() <> 200 then
        m.top.error = m.top.server + " answered " + msg.GetResponseCode().ToStr()
        return
    end if

    numRe = CreateObject("roRegex", "channel-number=" + Chr(34) + "([^" + Chr(34) + "]*)" + Chr(34), "")
    groupRe = CreateObject("roRegex", "group-title=" + Chr(34) + "([^" + Chr(34) + "]*)" + Chr(34), "")
    channels = []
    for each line in msg.GetString().Split(Chr(10))
        if Left(line, 8) = "#EXTINF:" then
            num = numRe.Match(line)
            group = groupRe.Match(line)
            comma = line.InStr(Chr(34) + ",")
            name = ""
            if comma >= 0 then name = line.Mid(comma + 2).Trim()
            if num.Count() > 1 then
                g = ""
                if group.Count() > 1 then g = group[1]
                channels.Push({ num: num[1], name: name, group: g })
            end if
        end if
    end for
    ' Sort by number, not text ("10" would come before "2").
    sorted = []
    for each c in channels
        c.n = c.num.ToInt()
        sorted.Push(c)
    end for
    sorted.SortBy("n")
    m.top.channels = sorted
end sub
