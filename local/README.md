# Audio2Face-3D 本地回放与 MetaHuman 导入准备

已配置官方源码、Mac Python 客户端和离线 3D 回放。当前默认预览使用 **Allison，支持与 James、Mark、Debra、Claire 一键切换**，保留此前 Face Cap 风格试作和裸模选项；这些都不是 MetaHuman 角色。MetaHuman 部分提供工程模板与导入脚本，尚未在 UE 内完成实测。

## 2026-10-13 播放与切换修复

- 角色加载期间记录用户最新的播放意图：主动暂停、逐帧操作或跳转情绪段落后，不再被自动恢复播放覆盖。
- 加载时禁用视角重置和线框操作，避免相机尚未建立时访问空对象；加载失败会清理部分资源，支持重新选择角色及单独播放音频。
- 角色切换复用同一个 WebGL 渲染器，并释放旧场景的阴影贴图、材质、几何和环境贴图。
- Allison、James、Mark 的角膜与眼球共用旋转中心，避免转眼时两层错位。当前数据基本不包含转眼动作，该项用独立转眼输入做矩阵验证。
- 本机 HTTP 服务支持音频字节范围请求，保证尚未完整缓存时可以跳到后段播放。

验证：`node tools/verify_viewer_regressions.mjs`、`.venv/bin/python tools/verify_preview_ranges.py`；浏览器实际验证慢加载暂停、失败恢复、五个写实角色及卡通模式连续切换。报告为 `verification-viewer-regressions.json`、`verification-preview-ranges.json` 和 `verification-viewer-browser.json`。本次没有更改原始音频、CSV 或表情形变文件，也未新增完整面部碰撞解算。

## 新增写实角色：Allison、James、Mark

打开 `http://127.0.0.1:8766/viewer/?asset=official-allison`，用左上角“头模”菜单选择角色。五个角色共用当前约 56 秒的音频与 1,680 帧动画。切换保留时间位置；播放中加载新角色时暂停音频，加载完成后继续。

| 角色 | 官方来源部分 | 本地适配部分 |
| --- | --- | --- |
| Allison | NVIDIA Character Transfer 示例中的扫描头部、皮肤、眼睛、眉毛 | 按官方提供的对应几何转移 52 个面部形变；适配 Claire 口腔、16 个舌头形变与发型 |
| James | NVIDIA Maya-ACE 头模及 James 模型包自身的 68 个形变 | Claire 皮肤贴图经参考拓扑转移 UV，深肤色材质与程序式短卷发 |
| Mark | NVIDIA Maya-ACE 头模及 Mark 模型包自身的 68 个形变 | Claire 皮肤贴图与程序式短卷发 |

James 与 Mark 使用各自的形变网格；Allison 通过三角形表面对应关系转移形变，保留自身的中性脸型。原 CSV、音频和 FBX 未改写。这些是 WebGL PBR 适配预览，James / Mark 的外观不是其官方完整材质套装；发型无物理模拟，牙齿与眼球运动采用近似处理，尚不等于 MetaHuman 或 NVIDIA RTX 原始渲染。

三个新角色已完成全部 1,680 帧的缓冲区、资源引用和有限顶点检查，报告见 `verification-realistic-characters.json`；该检查不代表完整碰撞检测。

官方源文件保存在 `assets/{allison,james,mark}-official/`，每个目录有逐文件来源、大小和 SHA-256 清单。恢复与重建（依赖此前已转换的 Claire 资产）：

```bash
.venv/bin/python tools/download_realistic_characters.py
.venv/bin/python tools/prepare_official_allison.py
.venv/bin/python tools/prepare_reference_characters.py
.venv/bin/python tools/prepare_debra_hair.py --role james
.venv/bin/python tools/prepare_debra_hair.py --role mark
.venv/bin/python tools/verify_realistic_characters.py
```

来源：[NVIDIA Allison USD](https://omniverse-content-production.s3.us-west-2.amazonaws.com/Assets/Audio2Face/Samples_2023.2/char_transfer/allison.usd)、[NVIDIA Maya-ACE](https://github.com/NVIDIA/Maya-ACE/tree/release/2.0/sample_project/maya_geom)、[James 模型包](https://huggingface.co/nvidia/Audio2Face-3D-v2.3.1-James)、[Mark 模型包](https://huggingface.co/nvidia/Audio2Face-3D-v2.3-Mark)。保留各源资产原有权利与许可；模型卡随包保存。

## Debra 与 Claire 共用数据切换

已接入 NVIDIA Audio2Face Samples_2023.2 中的 Reallusion Debra GameBase 原始头部、皮肤、眼睛、牙齿、舌头与原生表情。官方包共 44 个文件、105,938,243 字节，保存在 `assets/debra-official/`，附逐文件来源与 SHA-256。该官方示例没有独立头发模型；当前本地预览已额外制作并接入深棕黑短卷发。

打开 `http://127.0.0.1:8766/viewer/?asset=official-debra`，点击“切换至 Claire / Debra”或使用头模菜单。两者共用当前 56 秒数据、音频与时间位置；播放中切换会在加载期间暂停音频，完成后继续。URL 保存选中的角色，刷新可保留角色选择。

Debra 使用自身的原生形变，通过 `viewer/debra-retarget.js` 将当前 68 路输入中的 58 路映射到 Reallusion 表情或眼球转动；同一权重不保证与 Claire 具有相同的视觉幅度。未映射的是 `jawForward` 和 9 路独立舌头动作：`tongueTipLeft/Right`、`tongueRollLeft/Right`、`tongueLeft/Right`、`tongueIn`、`tongueStretch`、`tongueWide`。当前是手工语义重定向，不是执行 NVIDIA 的 Character Transfer OmniGraph，也没有重新推理或修改原始 CSV/FBX。

**不能直接复制 Claire 顶点形变的原因：** Claire 皮肤有 61,520 个顶点，Debra 原始头部与肩颈有 1,295 个顶点；顶点数量、编号、连接方式和位置均不同。Claire 的第 i 个顶点位移不能直接作用于 Debra 的第 i 个顶点。可共享的是“张嘴、微笑、眨眼”等动作权重，再驱动各自匹配的形变目标。若必须保留 Claire 的精确运动，需要先建立表面对应关系并进行形变转移。

转换为 `viewer/official-debra/`：Debra 原始皮肤的 69 个形变随中性网格一起做两次 Catmull–Clark 细分，皮肤得到 30,697 个位置顶点，再按材质和 UV 接缝拆分；转换法线并保留原始颜色、法线、粗糙度、AO、透明度及乘算颜色贴图。面角 UV 使用线性细分，WebGL PBR 是 MDL 的近似显示。低面数眼睑闭合时辅助眼球略向后移，避免细分后的表面穿插；原贴图眼周本身偏黑，未重新绘制。该预览不是完整的眼睑/口腔碰撞解算，不是 MetaHuman。

`verification-debra-retarget.json` 通过全部 1,680 帧及四分之一帧插值共 6,717 个采样，检查权重有限且在 0–1 内、零输入保持中性、每个规则引用存在的原生表情。这不等于所有表面均无碰撞。

```bash
.venv/bin/python tools/download_official_debra.py
.venv/bin/python tools/prepare_official_debra.py
node tools/verify_debra_retarget.mjs
```

来源：[NVIDIA 官方 Debra USD](https://omniverse-content-production.s3.us-west-2.amazonaws.com/Assets/Audio2Face/Samples_2023.2/reallusion/Debra_A2F_CC_GameBase/Debra_A2F.usd)。保留原有 NVIDIA / Reallusion 权利与许可。

## Debra 短卷发

新增本地制作的深棕黑色短卷发，默认开启。模型下方“短卷发”开关可即时隐藏或显示，切换 Claire 时自动隐藏此开关。发型根据 Debra 实际中性头皮拟合，包含贴合头皮的底层和 5,200 条带锥形发梢的立体卷曲发束；保持额头、眼睛和耳朵周围清晰可见。原始官方网格、贴图和动画数据未改写。

这是本项目制作的程序式附加发型，不属于 NVIDIA / Reallusion 官方包，也不是 Claire 毛发的顶点复制。随头部固定显示，没有发丝物理模拟。几何文件位于 `viewer/debra-hair/`，加载器为 `viewer/debra-hair.js`。复现命令：

```bash
.venv/bin/python tools/prepare_debra_hair.py
```

## 官方 Claire 完整资产

已从 NVIDIA 官方公开资源目录下载 `claire_lookdev.usda`、初始场景、头模、完整 groom、灯光及全部 EXR/PNG 依赖：63 个文件，4,288,438,999 字节。源文件保持原样，位于 `assets/claire-official/`；SHA-256、大小和逐文件来源在 `manifest.json`。

头模菜单选择“Claire · 官方完整资产”。仍由 `metahuman_emotions_56s.zip` 的 1,680 帧 / 68 路权重和音频驱动。皮肤 61,520 个顶点、舌头 5,602 个顶点的三角形顺序与已有官方动画拓扑完全一致，采用对应的中性网格，沿用官方 UV，按 UDIM 拆分并同步复制形变与法线，避免贴图接缝和顶点顺序错位。眉毛、睫毛和细毛根据最近皮肤顶点加权绑定，随面部运动。

转换版位于 `viewer/official-claire/`。面部颜色和法线保留 4K，其他主要贴图采用 2K；EXR 颜色在线性空间缩小后转成 sRGB PNG，法线与粗糙度保持线性。粗糙度读取官方组合贴图 R 通道。两只眼睛使用官方材质指定的 `c_eye_diffuseReflectionColor_rt.1013.exr`。毛发为官方曲线生成的相机朝向细带：主发抽样到三分之一，长曲线适量减少控制点，全部原始曲线仍在源 USD。

**渲染范围：** WebGL 使用 PBR 材质，未复刻 RTX / MDL 的完整次表面散射、折射和多重毛发散射。皮肤与舌头使用原始权重；下牙和舌头附加 `jawOpen` 近似下颌刚体运动，眼球暂保持正视。它是本机可播放的官方 Claire 预览；完整原场景可用于有 NVIDIA MDL/RTX 支持的 Omniverse 环境。源场景引用的内置 MDL 库由 Omniverse 提供，不是此下载目录里的独立文件。未生成 MetaHuman DNA 或 Unreal 角色。

来源：[NVIDIA 数字人材质教程](https://docs.omniverse.nvidia.com/workflows/latest/rtx_rt-dh-setup.html)；[官方 Claire 资源目录](https://omniverse-content-production.s3.us-west-2.amazonaws.com/Samples/Examples/2023_1/Rendering/Claire/claire_lookdev.usda)。资源保留 NVIDIA 原有权利，本项目不另行授予素材再分发许可。

重新下载与转换（下载约 4.29 GB，已有完整文件会跳过）：

```bash
.venv/bin/python tools/download_official_claire.py
.venv/bin/python tools/prepare_official_claire.py
```

转换新增依赖 `usd-core==26.8`、`OpenEXR==3.5.2`，已安装并写入锁定文件。`verification-official-claire.json` 记录拓扑、贴图及毛发转换信息；`verification-official-claire-playback.json` 校验通过 63 个源文件、68 路通道及全部 1,680 帧，确认 UV 拆分后的皮肤和舌头基础顶点与全部形变逐值相同。验证命令：`.venv/bin/python tools/verify_official_claire.py`。

## 此前的通用皮肤与风格试作

头模下拉框可选择“写实皮肤 · 通用人脸”或“Claire · 原始参考头模”。新模式采用 Three.js r180 官方示例中的 Face Cap 头模，并用内置 image_gen 编辑其原 UV 图集，生成通用肤色、毛孔、眉毛、唇色和虹膜纹理。它是合成皮肤，不是特定真人的照片或扫描；这次使用 base-color 贴图，没有声称具备扫描级完整皮肤材质或 MetaHuman 级渲染。

纹理文件：`viewer/models/skin-albedo-v1.png`。完整生成提示词：`viewer/models/skin-generation-prompt.txt`。模型与原图来源：`viewer/models/SOURCES.txt`。

写实头模匹配全部 52 个面部通道；16 个独立舌头形变仅由 Claire 模式支持。原 GLB 附带的动画不会播放，当前脸只由本包 CSV 权重驱动。眼球和牙齿仍是静态参考。

## 当前数据包

当前播放器已切换为 `metahuman_emotions_56s.zip`，原包保留在 `demo-data/`，新包在 `demo-data/emotions-56s/`。新包音频为 55.952 秒，1,680 帧 / 30 fps，播放区间 56 秒。页面支持跳转六个情绪段落；情绪为人工指定条件，眨眼已由服务端规则叠加到最终权重。

重新生成当前预览与校验：

```bash
.venv/bin/python tools/prepare_preview.py demo-data/emotions-56s
.venv/bin/python tools/validate_package.py demo-data/emotions-56s --output validation-emotions-56s.json
```

新包校验通过 13 个文件、1,680 帧和 290,640 个 FBX 关键帧数值。`validation.json` / `verification.json` 保留初始 4 秒包的验证记录；新包详见 `validation-emotions-56s.json`。

## 打开预览

双击 `Start Preview.command`，在浏览器打开 <http://127.0.0.1:8766/viewer/>。也可以在本目录运行：

```bash
.venv/bin/python serve_preview.py
```

点击“播放音频与动画”，支持暂停、逐帧、拖动时间、0.5/1/1.5 倍速、循环、旋转视角、线框，以及 68 路表情和 173 路 MetaHuman 控制曲线查看。停止服务可在启动终端按 Ctrl+C。端口被占用时用 `--port 8767` 并打开对应地址。

播放完全使用本机文件，网页无外部 CDN、上传或推理请求。首次安装已下载 Three.js 0.180.0；运行时无需 npm 或网络。服务只监听 127.0.0.1。

## 这次完成的环境

- `repos/Audio2Face-3D`：官方项目入口。
- `repos/Audio2Face-3D-Samples`：官方 Python 客户端。
- `repos/Audio2Face-3D-SDK`：官方 C++/CUDA SDK 源码。版本和安装结果见 `environment.json`。
- `.venv`：Python 3.12.14 / macOS arm64；安装官方客户端固定依赖与 `nvidia_ace==1.2.0`。官方客户端 CLI、imports 和依赖检查通过。
- `requirements-lock.txt`：客户端环境依赖版本。SDK 示例中的 3 个 WAV 仍为 Git LFS 指针；不影响本包回放。

**Apple M5 Pro 不能运行官方 CUDA/TensorRT 推理 SDK。** 官方 SDK 支持 Windows/Linux + NVIDIA GPU。本机已配置的是客户端和离线预览；没有编译 SDK、没有下载 ONNX 推理模型，也没有声称在 Mac 完成官方本地推理。仍可连接已部署的远端 Audio2Face-3D 服务。

有服务器地址后，在本目录运行（将 SERVER_HOST 换为实际主机）：

```bash
source .venv/bin/activate
python repos/Audio2Face-3D-Samples/scripts/audio2face_3d_microservices_interaction_app/a2f_3d.py health_check --url SERVER_HOST:52000
python repos/Audio2Face-3D-Samples/scripts/audio2face_3d_microservices_interaction_app/a2f_3d.py run_inference demo-data/audio.wav repos/Audio2Face-3D-Samples/scripts/audio2face_3d_microservices_interaction_app/config/config_claire.yml --url SERVER_HOST:52000
```

未提供服务器地址/API key，因此没有测试联网推理。不同服务版本的配置和认证要求应以对应服务为准。

## 预览的范围

初始 4 秒包保留在 `demo-data/`，以下段落描述初始包。初始数据为 30 fps、120 帧，动画最后一帧为 3.966667 秒，播放区间为 4 秒；音频为 16 kHz、单声道、PCM16、3.936 秒。

早期“Claire · 原始参考头模”网格由 NVIDIA 官方同版本的 blendshape 中性顶点与形变、Maya-ACE 官方对应拓扑重建；浏览器以 CSV 原始权重驱动，不进行新推理，不添加情绪或随机动作。皮肤与舌头有形变；辅助眼球和牙齿是静态参考网格，没有牙齿刚体动画。材质为中性预览材质，没有高精度皮肤贴图、头发、身体或 MetaHuman DNA。不能用这个预览替代 UE 角色上的最终验收。

原始包说明其服务端采用 Claire 回归模型与 SciPy CPU 求解器公式实现，neutral 情绪，未运行 Audio2Emotion；并非 NIM 逐位复刻。这些是包内来源声明，本次没有重跑服务端模型。

## 数据校验

`validation.json` 记录独立校验结果：全部 10 个文件的大小与 SHA256 通过；CSV/NPZ 数据与映射一致；173 条 FBX 曲线共 20,760 个关键帧与控制 CSV 一致。FBX 含 159 个 Null 控制节点，没有角色网格。

重新运行：

```bash
.venv/bin/python tools/validate_package.py demo-data/emotions-56s --output validation-emotions-56s.json
.venv/bin/python tools/prepare_preview.py demo-data/emotions-56s
```

## MetaHuman 导入

详见 `unreal/导入说明.txt`。`unreal/A2FMetaHuman/A2FMetaHuman.uproject` 是 UE 5.7 工程模板；没有角色资产。

1. 准备并装配一个 MetaHuman，放进关卡，选中该角色。
2. 在 UE 启用 Python、Control Rig 和 Sequencer Scripting，执行 `unreal/import_selected_metahuman.py`。
3. 脚本尝试创建 30 fps 序列，把 `face.fbx` 导入 Face Control Rig，并从第 0 帧加入音频；运行后生成曲线回读报告。
4. 在角色上播放，核对嘴唇、牙齿、舌头和左右控制方向，再保存关卡。

`face.fbx` 应使用 **Import Control Rig FBX + MetaHuman Controls Mapping**，不是普通网格或骨骼 AnimSequence 导入。

本机发现 UE 5.7.4、5.8 和 Creator 预设；没有可用的已装配角色工程。UE 5.7 commandlet 首次探测超过六分钟无输出，已终止；未查明启动原因。导入脚本仅依据本机 UE 5.7 API 编写并通过语法检查，**尚未在 UE 中运行验证**。真实 MetaHuman 回放仍需正常启动的编辑器和带有效面部 DNA 的已装配角色。

## 来源与许可

- [NVIDIA Audio2Face-3D SDK](https://github.com/NVIDIA/Audio2Face-3D-SDK)
- [官方 Samples](https://github.com/NVIDIA/Audio2Face-3D-Samples)
- [Claire v2.3.1 模型与参考形变](https://huggingface.co/nvidia/Audio2Face-3D-v2.3.1-Claire)
- [NVIDIA Maya-ACE](https://github.com/NVIDIA/Maya-ACE)
- [Epic Control Rig FBX 导入](https://dev.epicgames.com/documentation/metahuman/animating-your-character-with-apex)

官方源码、Three.js、模型参考资源各自的许可证保留在对应目录。`assets/claire/` 保存下载来源资源，`viewer/mesh.json` 和相关元数据说明转换方式与限制。

## 写实头模的嘴唇适配

Face Cap 的 `mouthClose` 是用于抵消张开的下颌的形变，不能直接照搬 Claire 独立的闭嘴权重。`viewer/facecap-retarget.js` 将其与 `jawOpen` 联动，并根据固定模型上 11 对上下唇接触点限制叠加的闭嘴、卷唇和下唇上抬幅度。修正逐个插值帧执行，仅影响写实头模；CSV、FBX、曲线面板与 Claire 回放保持原值。这是预览用的模型适配，不是完整的网格碰撞解算。

回归验证直接解码固定版本 GLB，检查全部 1680 帧及每帧四分之一处的插值，共 6717 个采样。报告见 `verification-lip-fix.json`；复现命令：

```bash
node tools/verify_facecap_retarget.mjs
```

写实预览还对极端嘴型做平滑收敛：嘴角间距超过中性宽度的 1.18 倍后逐渐压缩，趋近 1.32 倍；`jawOpen` 超过 0.38 后逐渐压缩，趋近 0.68。宽度按微笑、嘴角拉伸、酒窝和挤嘴等形变的合成几何结果计算，左右比例保持一致。低幅度部分不受这一步压缩影响；随后仍执行唇部接触约束。阈值为当前通用头模的预览调校值，不是人体解剖标准。整段采样最大嘴角宽度由中性的约 1.575 倍降为 1.319 倍。

## 三种女性风格试作

左上角头模菜单新增：写实女性、3D 卡通女生、二次元女生。三版使用同一个 Face Cap 表情拓扑，分别变换基础脸型和全部 52 个形变目标，重新生成浮点法线；同时调整眼睛比例、鼻部和下颌轮廓，添加程序式立体发型。眼球贴图按每张新 atlas 的虹膜中心投影到球面。二次元版使用 Toon 材质。

这是可播放的风格原型，不是三个独立扫描头模，也不是装配完成的 MetaHuman。头发、牙齿和眼球没有独立动作，模型没有身体、服装或物理发丝。共用用户原始音频和动画；所有嘴型适配仅用于显示。

素材由内置 image_gen 编辑生成：`viewer/models/skin-realistic-v1.png`、`skin-cartoon-v1.png`、`skin-anime-v1.png`。输入为原始 UV atlas 和上一版通用皮肤，完整提示词在 `viewer/models/style-generation-prompts.txt`。模型与贴图来源见 `viewer/models/SOURCES.txt`。

`verification-face-styles.json` 记录三版各 6717 个采样点、11 对唇部接触点的几何校验与嘴宽上限结果，均通过；该检查不等于全网格碰撞验证。


## 训练工作台（2026-10-18）

入口：`http://127.0.0.1:8766/viewer/training/`，人物回放顶部也有入口。使用同一个服务启动：

```bash
.venv/bin/python serve_preview.py
```

- **数据准备**：官方 Claire 数据集 / 自定义角色二选一；浏览器本地检查 WAV 与 NPY 配对、PCM 参数、形状、时长和顶点数量。文件不上传。自定义数据先复制到训练机，工作台同时支持平铺缓存和官方的 `cache/skin/<shot>/<shot>.<ext>` 结构，执行时统一为官方结构。PC2 / Maya MC/XML 会进一步由 NVIDIA 预处理验证。
- **配置与导出**：Diffusion 默认 400 轮、Regression 默认 50 轮，另有 5 轮流程检查预设；支持兼容 .pth 权重初始化。配置保存在本浏览器。运行包包含 `plan.json`、`worker.py`、`README.txt`；无需连接训练机即可导出。
- **真实执行**：填写 `user@host`、端口、Linux 工作目录，通过 SSH 环境检查后，一键执行获取官方源码 / Docker 构建、样例下载或自定义数据检查、分集、预处理、训练、ONNX 导出。Diffusion 再用一段留出音频生成 NPY 验证动画；Regression 在锁定版本尚无 Python 推理入口，需要 Maya-ACE 验证。没有 GPU 时不生成虚构任务或日志。
- **环境**：Linux / WSL2、NVIDIA GPU 至少 6 GB、Docker + NVIDIA Container Toolkit、Python 3、Git；官方样例还需要 Git LFS。SSH 使用现有密钥 / agent，严格检查 known_hosts，不接收密码或私钥。首次在训练机执行需要网络；最低显存不代表所有数据和配置均可运行。
- **任务与产物**：日志实时返回，可停止任务。远端保存 `<root>/jobs/<job>/` 下的配置、数据检查、分集、PCA、权重、部署模型与验证动画；本机任务记录在 `training-runs/`，不作为静态文件公开。SSH 断开或服务重启时标记远端状态未知，需确认停止后才允许新任务。
- **数据边界**：当前 56 秒回放包属于推理输出，不能直接视为真实训练标注。本工作台要求至少 5 个配对片段，并以 seed 42 按完整 shot 留出约 20%，仅训练片段参与 PCA。这是工作台规则，不是官方最低样本数。目录检查不证明顶点顺序、真实同步、有限数值和标注质量，仍需 DCC 检查。
- **角色接入**：ONNX / 顶点缓存不是播放器的 68 路 CSV。后续仍需对应角色的 Blendshape 求解 / 控制器映射；MetaHuman 还需要 UE 工程与角色资产。

执行源码固定在 [NVIDIA Training Framework 112c5eb3408a](https://github.com/NVIDIA/Audio2Face-3D-Training-Framework/tree/112c5eb3408afd065ac8974b2c6ea9ab0e3965c6)。本地源码保存在 `repos/Audio2Face-3D-Training-Framework/`；每次 GPU 任务执行前核对同一提交。编排直接调用 Docker 内的 `runners/`，检查子进程退出码和实际产物，避免官方根目录包装脚本忽略子进程退出码的问题。保留官方样例原有中文 / 英文标签，修正生成的 clips_template 默认英文造成的信息丢失。页面社区参考列出 [FaceFormer](https://github.com/EvelynFan/FaceFormer)、[CodeTalker](https://github.com/Doubiiu/CodeTalker) 作者仓库与训练差异，并将社区用户报告与已确认的框架行为区分。

验证命令：

```bash
.venv/bin/python tools/verify_training_workbench.py
node tools/verify_viewer_regressions.mjs
.venv/bin/python tools/verify_preview_ranges.py
```

测试覆盖数据配对与损坏文件、确定性分集、验证集隔离、两条模型路线的编排合同、失败中止、取消、检查过期、同源 API 和原有音频 Range。GPU / SSH 过程在合同测试中使用测试替身；本机没有可用 NVIDIA GPU，**尚未完成真实 GPU 端到端训练验收**。5 轮预设用于检查流程，不是质量保证。

## v3 推理结果页（2026-10-19）

入口：`http://127.0.0.1:8766/viewer/inference/`，人物回放和训练工作台导航均有入口，复用现有 `serve_preview.py` 服务。

导入 `v3_20demos_20s_20261018_data_01-05.zip` 中实际包含的 5 段 Claire 结果：中性、开心、惊讶、情绪过渡、难过，每段 20 秒、1,200 帧、60 fps。支持片段切换、三维旋转缩放、原视频同步对照、逐帧、拖动进度、0.5/1/1.5 倍速、循环、静音，显示人工情绪条件、音频波形、原文和逐帧位移统计；可下载原 NPZ、CSV、JSON、WAV 和视频。

数据保存于 `demo-data/v3-20s-01-05/`。导入器只解包数据、元信息和许可证，不运行随包 Python/HTML。校验每段 run.json 的 5 个文件哈希、NPZ 形状/有限值/时间戳、音频时长及 Maya v3 的完整三角形顶点顺序。使用 neutral + 原始位移（24,002 皮肤顶点、5,602 舌头顶点），没有使用旧 v2 的 Blendshape 或嘴形限制。每 30 帧生成一个带下一帧重叠的 float32 二进制块，全部块逐值验证无损；网页按需加载，最多保留 4 块。音频为主时钟，缺块时同时暂停音画，切换片段会取消旧请求。

下牙使用 5 个下颌锚点拟合刚体运动，舌头不重复应用下颌变换。眼球角度来自原结果，转轴用官方眼球网格包围盒中心近似。皮肤贴图复用本地 Claire 材质，通过同身份 v3 参考网格适配 UV；仅为浏览器预览，不等同于原视频渲染或 UE/MetaHuman。原视频保留其原始 30 fps。情绪是人工编排输入，五段音频各不相同，不能当作同音频的严格情绪 A/B 实验。

重新导入与数据检查：

```bash
.venv/bin/python tools/prepare_inference_gallery.py /path/to/downloads/hy/outputs/v3_20demos_20s_20261018_data_01-05.zip
node tools/verify_inference_gallery.mjs
```

详细校验记录在 `demo-data/v3-20s-01-05/web/validation.json`。缓存测试覆盖五段的跨块连续性、末帧、随机跳转、内存上限、损坏数据、请求去重与取消。浏览器实测五段选择、原视频对照、指定时间跳转、逐帧与循环倍速；没有在本机重新执行推理或训练。
