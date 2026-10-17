' Starts the Work log server in the background, with no window. Its messages go to data\server.log.
' Which networks it accepts is NOT set here any more: run network.bat to choose
' (this computer only / local network / Tailscale). The choice is saved in data\network_mode.txt.
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
folder = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = folder
sh.Run """" & folder & "\venv\Scripts\pythonw.exe"" """ & folder & "\serve.py"" --mode saved --port 80", 0, False
