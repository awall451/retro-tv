sub init()
    m.top.functionName = "fetch"
end sub

sub fetch()
    http = CreateObject("roUrlTransfer")
    http.SetUrl(m.top.server + "/iptv/xmltv.xml")
    http.EnableEncodings(true)
    port = CreateObject("roMessagePort")
    http.SetMessagePort(port)
    if not http.AsyncGetToString() then
        m.top.error = "Could not start the guide request"
        return
    end if
    msg = wait(30000, port)
    if msg = invalid then
        http.AsyncCancel()
        m.top.error = "The guide did not arrive"
        return
    end if
    if msg.GetResponseCode() <> 200 then
        m.top.error = "The guide answered " + msg.GetResponseCode().ToStr()
        return
    end if

    xml = CreateObject("roXMLElement")
    if not xml.Parse(msg.GetString()) then
        m.top.error = "The guide could not be read"
        return
    end if

    now = CreateObject("roDateTime").AsSeconds()
    first = now - 2 * 3600
    last = now + 8 * 3600
    guide = {}
    for each p in xml.GetNamedElements("programme")
        a = p.GetAttributes()
        start = xmltvSeconds(a.start)
        ends = xmltvSeconds(a["stop"])
        if ends > first and start < last then
            ch = a.channel
            if not guide.DoesExist(ch) then guide[ch] = []
            cats = []
            movie = false
            for each c in p.GetNamedElements("category")
                t = c.GetText()
                if t = "Movie" then movie = true
                if t <> "Movie" and t <> "Series" and cats.Count() < 3 then cats.Push(t)
            end for
            icon = ""
            ic = p.GetNamedElements("icon")
            if ic.Count() > 0 then icon = ic[0].GetAttributes().src
            year = Left(childText(p, "date"), 4)
            if year = "0" then year = ""
            onscreen = ""
            ns = ""
            for each e in p.GetNamedElements("episode-num")
                scheme = e.GetAttributes().system
                if scheme = invalid then scheme = ""
                if scheme = "onscreen" then onscreen = e.GetText()
                if scheme = "xmltv_ns" then ns = e.GetText()
            end for
            ep = ""
            if not movie then ep = episodeCode(onscreen, ns)
            guide[ch].Push({
                start: start,
                ends: ends,
                title: childText(p, "title"),
                sub: childText(p, "sub-title"),
                desc: childText(p, "desc"),
                ep: ep,
                year: year,
                movie: movie,
                genres: cats.Join(", "),
                icon: icon,
                rating: ratingText(p)
            })
        end if
    end for
    ' Same cells as the browser viewer: a run of shorts (under 15 minutes)
    ' with one title inside one half hour is one cell; a hole of more than
    ' a minute is a "No information" cell.
    cells = {}
    for each ch in guide
        guide[ch].SortBy("start")
        cells[ch] = buildCells(guide[ch])
    end for
    m.top.guide = cells
end sub

function buildCells(progs as object) as object
    out = []
    last = invalid
    for each p in progs
        if last <> invalid and p.start > last.ends + 60 then
            out.Push({ start: last.ends, ends: p.start, title: "No information", items: [], gap: true })
            last = invalid
        end if
        short = p.ends - p.start < 900
        bucket = Int(p.start / 1800)
        if last <> invalid and short and last.short and last.title = p.title and last.bucket = bucket then
            last.items.Push(p)
            last.ends = p.ends
        else
            title = p.title
            if title = "" then title = "No title"
            last = { start: p.start, ends: p.ends, title: title, items: [p], short: short, bucket: bucket, gap: false }
            out.Push(last)
        end if
    end for
    return out
end function

' Season and episode as "S01E02" (two digits at least), or "S01E02-E03"
' for a double episode; "" when there are none (as episodeCode in the
' viewer's data.js). Onscreen first: ErsatzTV writes a season 0 special as
' season -1 in the zero-based xmltv_ns.
function episodeCode(onscreen as string, ns as string) as string
    s = -1
    e = -1
    e2 = -1
    hit = CreateObject("roRegex", "^S(\d+)\s*E(\d+)(?:\s*-?\s*E?(\d+))?$", "i").Match(onscreen.Trim())
    if hit.Count() > 2 then
        s = hit[1].ToInt()
        e = hit[2].ToInt()
        if hit.Count() > 3 and hit[3] <> "" then e2 = hit[3].ToInt()
    else
        hit = CreateObject("roRegex", "^\s*(\d+)\s*(?:/\s*\d*\s*)?\.\s*(\d+)(?:\s*-\s*(\d+))?\s*(?:/\s*\d*\s*)?\.", "").Match(ns)
        if hit.Count() < 3 then return ""
        s = hit[1].ToInt() + 1
        e = hit[2].ToInt() + 1
        if hit.Count() > 3 and hit[3] <> "" then e2 = hit[3].ToInt() + 1
    end if
    code = "S" + two(s) + "E" + two(e)
    if e2 > e then code = code + "-E" + two(e2)
    return code
end function

function two(n as integer) as string
    t = n.ToStr()
    if Len(t) < 2 then t = "0" + t
    return t
end function

function childText(p as object, name as string) as string
    kids = p.GetNamedElements(name)
    if kids.Count() = 0 then return ""
    return kids[0].GetText()
end function

function ratingText(p as object) as string
    r = p.GetNamedElements("rating")
    if r.Count() = 0 then return ""
    v = r[0].GetNamedElements("value")
    if v.Count() = 0 then return ""
    return v[0].GetText()
end function

' "20261106183352 -0500" -> seconds since 1970, UTC.
function xmltvSeconds(s as string) as integer
    if s = invalid or Len(s) < 14 then return 0
    iso = Mid(s, 1, 4) + "-" + Mid(s, 5, 2) + "-" + Mid(s, 7, 2) + "T" + Mid(s, 9, 2) + ":" + Mid(s, 11, 2) + ":" + Mid(s, 13, 2) + "Z"
    d = CreateObject("roDateTime")
    d.FromISO8601String(iso)
    secs = d.AsSeconds()
    if Len(s) >= 20 then
        sign = Mid(s, 16, 1)
        offset = Mid(s, 17, 2).ToInt() * 3600 + Mid(s, 19, 2).ToInt() * 60
        ' local time = UTC + offset, so UTC = local - offset
        if sign = "-" then
            secs = secs + offset
        else
            secs = secs - offset
        end if
    end if
    return secs
end function
