Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

Dim userProfile, pythonPath, projectDir, backendPath

' Use environment variable to avoid hardcoding Chinese username
userProfile = WshShell.ExpandEnvironmentStrings("%USERPROFILE%")
pythonPath = userProfile & "\AppData\Roaming\kimi-desktop\daimon-share\daimon\runtime\python\.venv\Scripts\python.exe"

projectDir = fso.GetParentFolderName(WScript.ScriptFullName)
backendPath = projectDir & "\backend\main.py"

If Not fso.FileExists(pythonPath) Then
    MsgBox "Python not found: " & pythonPath, vbCritical, "Error"
    WScript.Quit 1
End If

If Not fso.FileExists(backendPath) Then
    MsgBox "Backend not found: " & backendPath, vbCritical, "Error"
    WScript.Quit 1
End If

' Start backend
WshShell.Run Chr(34) & pythonPath & Chr(34) & " " & Chr(34) & backendPath & Chr(34), 0, False

' Wait for port 5889
Dim waited, portReady, tempFile
portReady = False
waited = 0
Do While waited < 30 And Not portReady
    WScript.Sleep 500
    waited = waited + 1
    tempFile = fso.GetSpecialFolder(2) & "\port_check.txt"
    WshShell.Run "cmd /c netstat -an | findstr 127.0.0.1:5889 > """ & tempFile & """", 0, True
    If fso.FileExists(tempFile) Then
        If fso.GetFile(tempFile).Size > 0 Then
            portReady = True
        End If
        fso.DeleteFile(tempFile)
    End If
Loop

' Open browser
If portReady Then
    WshShell.Run "http://127.0.0.1:5889/", 1, False
Else
    MsgBox "Backend started but port not ready. Please refresh.", vbInformation, "Quant Workbench"
End If
