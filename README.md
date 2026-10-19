# Audio2Face Studio

A browser gallery for NVIDIA Audio2Face-3D inference results, with the source of a local character viewer and training workbench.

**[Open the live demo](https://Primer-1-wy.github.io/audio2face-studio/)**

## 在线演示

五段 Claire 推理结果：中性、开心、惊讶、情绪过渡、难过。每段 20 秒、1,200 帧、60 fps，共 100 秒。支持交互式三维回放、随包原视频对照、逐帧、拖动进度、倍速、循环、情绪曲线、语音内容和数据下载。

皮肤 24,002 顶点、舌头 5,602 顶点。位移驱动对应的 NVIDIA Maya-ACE v3 网格，不套用旧版拓扑。下牙由五个下颌点拟合刚体运动；眼球采用原始角度，转轴近似为网格中心。皮肤材质来自 Claire 官方示例，经 UV 适配与纹理缩小后用于网页预览。

线上数据使用 **16 位量化、帧间差分和 gzip** 保留全部 60 fps。几何量化步长为 0.001 cm，单坐标误差最大约 **0.005 mm**；眼球角度误差最大约 **0.005°**。这不包括眼球转轴、下牙刚体拟合或材质适配误差。原始 float32 NPZ 仍保留在本地项目，不混入 Git 历史。网页最多缓存四个动画块，按需载入；缓冲时暂停音频以维持同步。

情绪曲线是**人工设置的输入条件**，不是语音情绪识别结果。五段使用不同语音，不构成同音频情绪 A/B 实验。原视频为 30 fps。示例语音与推理数据来自项目所有者提供的 `v3_20demos_20s_20261018_data_01-05.zip`；压缩精度报告位于 `docs/data/validation.json`（解包后）。

## 本地运行

```bash
git clone https://github.com/Primer-1-wy/audio2face-studio.git
cd audio2face-studio
python3 tools/unpack_site.py
node tools/verify_site.mjs
python3 tools/serve_site.py
```

打开 http://localhost:8000/。静态演示不需要 CUDA、NVIDIA GPU 或额外 npm 安装；Three.js 0.180.0 的运行时随演示提供。浏览器需支持 WebGL 2 和 DecompressionStream。

静态资产在仓库中以 `site-assets-*.part` 保存，`site-bundle.json` 记录每段大小和 SHA-256。解包器只接受清单中的片段，检查每段与整体哈希，拒绝越界路径和非普通文件。分包让单个文件保持在 20 MiB 以内；日常页面代码在 `docs/` 中直接编辑。

## 代码结构

- `docs/`：GitHub Pages 页面、播放器和运动解码器。
- `local/`：此前本地人物回放、数据转换、训练工作台、Python 服务和 Unreal 导入辅助源码。
- `tools/unpack_site.py`：校验并展开演示资产。
- `tools/verify_site.mjs`：解码、分块、链接及体积检查。
- `.github/workflows/deploy.yml`：校验后自动发布 GitHub Pages。

`local/` 不包含 Python 环境、第三方仓库、模型权重、完整角色资产或训练任务记录。完整本地工程需要按 `local/README.md` 获取官方依赖并提供原始输入数据；无需这些内容即可运行上述静态演示。训练工作台的真实训练需要 Linux/WSL2、NVIDIA GPU 与 Docker。GitHub Pages 只运行静态前端，不能执行 SSH、CUDA 或训练服务。

## 发布

仓库 Settings → Pages → Source 选择 **GitHub Actions**。推送到 main 会校验资产并发布。源码直接保存在仓库中，资产会在发布时校验并解包。

## 来源与许可

这是个人演示项目，非 NVIDIA 官方产品，亦非 Epic MetaHuman 渲染。NVIDIA 角色、模型派生数据与材质和 Three.js 各自遵循其原有条款；详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 和 `docs/licenses/`。第三方资产没有被重新授予一个统一的开源许可证。
