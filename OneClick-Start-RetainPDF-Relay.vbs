Option Explicit

Dim fso, shell, baseDir, configPath, exePath, scriptPath, pythonwPath, command

Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

baseDir = fso.GetParentFolderName(WScript.ScriptFullName)
configPath = fso.BuildPath(baseDir, "retainpdf-relay-proxy.json")
exePath = fso.BuildPath(baseDir, "dist\RetainPdfRelayProxy.exe")
scriptPath = fso.BuildPath(fso.BuildPath(baseDir, "src"), "retainpdf_relay_proxy.py")

shell.CurrentDirectory = baseDir

If fso.FileExists(exePath) Then
  command = Quote(exePath) & " --configure-and-run --config " & Quote(configPath)
Else
  pythonwPath = FindOnPath("pythonw.exe")
  If pythonwPath = "" Then
    MsgBox "pythonw.exe was not found. Install Python for Windows or build dist\RetainPdfRelayProxy.exe first.", _
      vbCritical, "RetainPDF Relay Proxy"
    WScript.Quit 1
  End If
  command = Quote(pythonwPath) & " " & Quote(scriptPath) & " --configure-and-run --config " & Quote(configPath)
End If

shell.Run command, 1, False

Function Quote(value)
  Quote = """" & value & """"
End Function

Function FindOnPath(executable)
  On Error Resume Next
  Dim exec, result
  result = ""
  Set exec = shell.Exec("cmd /c where " & executable)
  If Err.Number = 0 Then
    Do While exec.Status = 0
      WScript.Sleep 25
    Loop
    If Not exec.StdOut.AtEndOfStream Then
      result = Trim(exec.StdOut.ReadLine())
    End If
  End If
  On Error GoTo 0
  FindOnPath = result
End Function
