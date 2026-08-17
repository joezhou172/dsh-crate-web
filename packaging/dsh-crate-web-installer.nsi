; DSH Crate Web - 本地离线安装器（NSIS）。
; 构建：build-installer.ps1（会自动 npm pack 并调用 makensis）。
Unicode true
!include "LogicLib.nsh"
!include "FileFunc.nsh"
!insertmacro GetParameters
!insertmacro GetOptions

!ifndef VERSION
  !define VERSION "0.1.1"
!endif
!ifndef CRATE_TGZ
  !error "构建时请通过 /DCRATE_TGZ=... 传入插件 tgz 路径"
!endif

Name "DSH Crate Web 安装器"
OutFile "dist\dsh-crate-web-installer-${VERSION}.exe"
InstallDir "$PROFILE\.dsh"
ShowInstDetails show
CRCCheck on
Var NodePath

DirText "DSH 数据目录" "选择 DeepSeek Harness 的数据目录。安装器已自动检测默认值，一般无需修改。$\r$\n$\r$\n若不确定，请保持默认。" "浏览..." "浏览 DSH 数据目录"

Page directory
Page instfiles

Function .onInit
  ; 0) 用户显式传 /D= 时，NSIS 已设置 $INSTDIR 并从命令行移除 /D=。
  ;    只要 $INSTDIR 不是默认值就说明指定了目录，直接采用，不再自动检测。
  ${IfNot} $INSTDIR == "$PROFILE\.dsh"
    Goto done
  ${EndIf}
  ; 1) $DSH_HOME 环境变量优先
  ReadEnvStr $0 "DSH_HOME"
  ${IfNot} $0 == ""
    StrCpy $INSTDIR "$0"
    Goto done
  ${EndIf}
  ; 2) 扫描 %APPDATA% 下的桌面版数据目录
  ReadEnvStr $1 "APPDATA"
  ${If} $1 == ""
    Goto done
  ${EndIf}
  FindFirst $2 $3 "$1\*"
loopFind:
  StrCmp $3 "" closeFind
  IfFileExists "$1\$3\dsh\profiles\web\package.json" 0 +3
    StrCpy $INSTDIR "$1\$3\dsh"
    Goto closeFind
  IfFileExists "$1\$3\dsh-home\profiles\web\package.json" 0 +3
    StrCpy $INSTDIR "$1\$3\dsh-home"
    Goto closeFind
  IfFileExists "$1\$3\profiles\web\package.json" 0 +3
    StrCpy $INSTDIR "$1\$3"
    Goto closeFind
  FindNext $2 $3
  Goto loopFind
closeFind:
  FindClose $2
done:
FunctionEnd

Section "Install DSH Crate Web"
  SetOutPath "$LOCALAPPDATA\dsh-crate-web-installer"
  File "${CRATE_TGZ}"
  File "installer\helper.mjs"

  ; 定位 node.exe（优先常见安装目录，其次 PATH）
  StrCpy $NodePath ""
  ${If} ${FileExists} "$PROGRAMFILES64\nodejs\node.exe"
    StrCpy $NodePath "$PROGRAMFILES64\nodejs\node.exe"
  ${ElseIf} ${FileExists} "$PROGRAMFILES\nodejs\node.exe"
    StrCpy $NodePath "$PROGRAMFILES\nodejs\node.exe"
  ${EndIf}
  StrCmp $NodePath "" 0 nodeFound
  nsExec::ExecToStack 'where node'
  Pop $0
  Pop $1
  StrCmp $0 0 0 nodeMissing
  StrCpy $NodePath "$1"
nodeMissing:
  StrCmp $NodePath "" 0 nodeFound
  SetErrorLevel 1
  MessageBox MB_ICONSTOP "未找到 Node.js。$\r$\n$\r$\n安装器需要本机的 Node.js（DSH 插件机制依赖它）。$\r$\n请先安装 Node.js 后重新运行。" /SD IDOK
  Abort
nodeFound:
  DetailPrint "Node.js: $NodePath"
  DetailPrint "DSH 数据目录: $INSTDIR"

  nsExec::ExecToLog '"$NodePath" "$LOCALAPPDATA\dsh-crate-web-installer\helper.mjs" --dsh-home "$INSTDIR" --log "$LOCALAPPDATA\dsh-crate-web-installer\install.log"'
  Pop $0
  StrCmp $0 0 0 installFailed
  MessageBox MB_OK "DSH Crate Web 已安装到 DSH 的 web profile。$\r$\n$\r$\n请重启 DeepSeek Harness 使插件生效。" /SD IDOK
  Goto done
installFailed:
  SetErrorLevel 1
  MessageBox MB_ICONSTOP "安装失败（退出码 $0）。$\r$\n$\r$\n请查看上方日志（静默安装可用 /LOG=日志文件），或把日志发给我。" /SD IDOK
done:
SectionEnd