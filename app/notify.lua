-- Notification mirror, running on the glasses' Lua 5.3 VM.
--
-- This app is deliberately dumb: the host sends a fully prepared screen and
-- this draws it. Wrapping, expiry, ordering and truncation all happen host-side
-- in halo_host/notifications.py.
--
-- Payload format: the header line, then one body line per row, newline
-- separated.
--
-- NAMING WARNING: every frame.* call in this file is a Frame-era placeholder
-- and has NOT been verified against the Halo Lua SDK. Do not "correct" these
-- names on sight. Check https://docs.brilliant.xyz/halo/halo-sdk-lua first,
-- and change the emulator's API table in the same pass. See CLAUDE.md.

local header = "waiting for host"
local body = {}

local function split_lines(s)
    local out = {}
    for line in (s .. "\n"):gmatch("([^\n]*)\n") do
        out[#out + 1] = line
    end
    return out
end

local function redraw()
    frame.display.clear()
    frame.display.text("NOTIFICATIONS", 16, 16, 3)
    frame.display.text(header, 16, 54, 1)
    frame.display.text(string.rep("-", 50), 16, 64, 1)

    if #body == 0 then
        frame.display.text("(nothing right now)", 16, 76, 2)
    else
        for i = 1, #body do
            frame.display.text(body[i], 16, 76 + (i - 1) * 22, 2)
        end
    end

    frame.display.show()
end

frame.bluetooth.receive_callback(function(payload)
    local lines = split_lines(payload)
    header = lines[1] or ""
    body = {}
    for i = 2, #lines do
        body[#body + 1] = lines[i]
    end
    redraw()
    -- Report back how much was drawn so the host can assert on it.
    frame.bluetooth.send("drew:" .. #body)
end)

redraw()
frame.bluetooth.send("notify-ready")
print("notify.lua running on " .. _VERSION)
