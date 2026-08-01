-- Cyborg demo app, running on the glasses' Lua 5.3 VM.
--
-- NAMING WARNING: every frame.* call in this file is a Frame-era placeholder
-- and has NOT been verified against the Halo Lua SDK. Do not "correct" these
-- names on sight. Check https://docs.brilliant.xyz/halo/halo-sdk-lua first,
-- and change the emulator's API table in the same pass. See CLAUDE.md.

local MAX_LINES = 8
local lines = {}

local function push(line)
    lines[#lines + 1] = line
    while #lines > MAX_LINES do
        table.remove(lines, 1)
    end
end

local function redraw()
    frame.display.clear()
    frame.display.text("CYBORG // HALO", 16, 16, 3)
    frame.display.text(string.rep("-", 38), 16, 52, 2)

    for i = 1, #lines do
        frame.display.text(lines[i], 16, 76 + (i - 1) * 22, 2)
    end

    frame.display.text(
        string.format("uptime %.1fs   %dx%d", frame.time.utc(),
                      frame.display.width, frame.display.height),
        16, 368, 1)
    frame.display.show()
end

-- Echo whatever the host sends, and acknowledge with the byte count so the
-- host has something to assert on.
frame.bluetooth.receive_callback(function(data)
    push("> " .. data)
    redraw()
    frame.bluetooth.send("ok:" .. #data)
end)

push("app started")
redraw()
frame.bluetooth.send("ready")
print("main.lua running on " .. _VERSION)
