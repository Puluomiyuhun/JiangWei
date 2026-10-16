# 构建输入

此处只保存复现本项目R剧本所需的输入，不是可运行游戏。

- `build-inputs/game/Data.e5`：2026-10-16测试MOD使用的人物表，含此前新增或替换的人物槽位。构建输出应与输入保持一致；改人物时须另行审查。
- `build-inputs/game/E5/Pmap.e5`：背景格点、尺寸与阻挡信息，供斜角路线校验；没有背景图片。
- `build-inputs/original-RS/R_00.EEX`：原版初始化模板。
- `build-inputs/original-RS/R_33.EEX`：历史线接入模板，正文接入17块原字节保留。
- `build-inputs/game/audio-files.json`：本机实际存在的音频文件名清单，仅用于无游戏环境的静态编号检查；无音频文件。

原位置和原文件哈希见仓库来源清单。默认构建只读取这些输入并写入project/mod_build/build，不修改输入和游戏安装。
