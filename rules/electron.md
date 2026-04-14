# Electron Rules

## Process Boundary
- main / preload / renderer 职责分清
- 不把敏感能力直接暴露给 renderer
- IPC 通道名清晰稳定

## Build / Package
- 打包问题优先检查配置、证书、脚本、平台差异
- 签名、notarize、builder 配置优先最小修改
- 平台差异必须明确区分 mac / win

## Debug Priority
1. 读构建日志
2. 看配置与证书
3. 看平台脚本
4. 再动代码
