; xD-Tools Windows installer.
;
; Built by scripts/build_installer.ps1, which passes in every path and the
; version -- nothing here is hardcoded to one machine, so the script can be
; run from a checkout or from CI without editing.
;
; NSIS (Nullsoft Scriptable Install System) rather than WiX or Inno Setup:
; it is open source (zlib licence), installable from winget in one line,
; and it packages a plain directory tree, which is exactly what PyInstaller
; produces in onedir mode. An MSI would buy Group Policy deployment, which
; nobody has asked for, at the price of a much heavier toolchain.
;
; Deliberately NOT here:
;   * a licence page -- this repository has no LICENSE file, and inventing
;     one in an installer would be worse than showing none;
;   * a .mdproj file association -- mdtools/main.py ignores sys.argv, so
;     double-clicking a project would open the app on its startup screen
;     rather than on that project. Add the association the day the app
;     learns to open a file it was given, not before.

Unicode true

!include "MUI2.nsh"
!include "FileFunc.nsh"
!include "LogicLib.nsh"
!include "x64.nsh"

!ifndef VERSION
  !define VERSION "0.0.0"
!endif
!ifndef SOURCE_DIR
  !error "SOURCE_DIR must be passed in: the PyInstaller onedir output"
!endif
!ifndef OUT_FILE
  !error "OUT_FILE must be passed in: where to write the installer"
!endif

!define APP_NAME "xD-Tools"
!define APP_EXE "MDTools.exe"
!define PUBLISHER "Artur Jakubowicz"
!define UNINSTALL_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}"

Name "${APP_NAME} ${VERSION}"
OutFile "${OUT_FILE}"
InstallDir "$PROGRAMFILES64\${APP_NAME}"
; Reinstalling over an existing copy keeps wherever it was put the first time.
InstallDirRegKey HKLM "Software\${APP_NAME}" "InstallDir"
RequestExecutionLevel admin
SetCompressor /SOLID lzma

VIProductVersion "${VERSION}.0"
VIAddVersionKey "ProductName" "${APP_NAME}"
VIAddVersionKey "ProductVersion" "${VERSION}"
VIAddVersionKey "FileVersion" "${VERSION}"
VIAddVersionKey "CompanyName" "${PUBLISHER}"
VIAddVersionKey "LegalCopyright" "${PUBLISHER}"
VIAddVersionKey "FileDescription" "${APP_NAME} installer"

!define MUI_ABORTWARNING
!ifdef APP_ICON
  !define MUI_ICON "${APP_ICON}"
  !define MUI_UNICON "${APP_ICON}"
!endif

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN "$INSTDIR\${APP_EXE}"
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

; The three languages the app itself speaks. The first one listed is what
; the installer falls back to when Windows is set to anything else.
!insertmacro MUI_LANGUAGE "English"
!insertmacro MUI_LANGUAGE "Polish"
!insertmacro MUI_LANGUAGE "Japanese"

Function .onInit
  ${IfNot} ${RunningX64}
    MessageBox MB_ICONSTOP "${APP_NAME} needs 64-bit Windows."
    Abort
  ${EndIf}
  !insertmacro MUI_LANGDLL_DISPLAY
FunctionEnd

Section "${APP_NAME}" SecApp
  SectionIn RO
  SetOutPath "$INSTDIR"
  ; The whole PyInstaller onedir tree: the .exe plus _internal, which holds
  ; Qt, the bundled cd-paranoia/flac/SoX/cdrecord binaries and the assets.
  File /r "${SOURCE_DIR}\*.*"

  WriteRegStr HKLM "Software\${APP_NAME}" "InstallDir" "$INSTDIR"
  WriteRegStr HKLM "Software\${APP_NAME}" "Version" "${VERSION}"

  WriteUninstaller "$INSTDIR\Uninstall.exe"
  WriteRegStr HKLM "${UNINSTALL_KEY}" "DisplayName" "${APP_NAME}"
  WriteRegStr HKLM "${UNINSTALL_KEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKLM "${UNINSTALL_KEY}" "Publisher" "${PUBLISHER}"
  WriteRegStr HKLM "${UNINSTALL_KEY}" "DisplayIcon" "$INSTDIR\${APP_EXE}"
  WriteRegStr HKLM "${UNINSTALL_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKLM "${UNINSTALL_KEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr HKLM "${UNINSTALL_KEY}" "QuietUninstallString" '"$INSTDIR\Uninstall.exe" /S'
  WriteRegDWORD HKLM "${UNINSTALL_KEY}" "NoModify" 1
  WriteRegDWORD HKLM "${UNINSTALL_KEY}" "NoRepair" 1
  ; What Add/Remove Programs shows as the size, in KB.
  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  IntFmt $0 "0x%08X" $0
  WriteRegDWORD HKLM "${UNINSTALL_KEY}" "EstimatedSize" "$0"

  CreateShortcut "$SMPROGRAMS\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}"
SectionEnd

Section "Desktop shortcut" SecDesktop
  CreateShortcut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}"
SectionEnd

Section "Uninstall"
  ; Only ever remove a directory this installer actually filled -- an
  ; $INSTDIR pointed somewhere else by hand would otherwise take a
  ; recursive delete with it.
  ${If} ${FileExists} "$INSTDIR\${APP_EXE}"
    RMDir /r "$INSTDIR"
  ${Else}
    Delete "$INSTDIR\Uninstall.exe"
    RMDir "$INSTDIR"
  ${EndIf}

  Delete "$SMPROGRAMS\${APP_NAME}.lnk"
  Delete "$DESKTOP\${APP_NAME}.lnk"
  DeleteRegKey HKLM "${UNINSTALL_KEY}"
  DeleteRegKey HKLM "Software\${APP_NAME}"

  ; %LOCALAPPDATA%\MDTools is left alone on purpose: it holds the user's
  ; own templates.json, their settings and their Telegram session, none of
  ; which this installer put there and any of which they may want after
  ; reinstalling.
SectionEnd
