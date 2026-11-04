# Spotify Charts: RQ5 & RQ6

国家／地区 Top 50 榜单的交互式比较。

- **RQ5**：比较 Energy、Danceability、Valence、Acousticness 的国家中位数和歌曲分布。
- **RQ6**：比较两国榜单的共同歌曲，以及歌曲的跨国上榜覆盖情况。

## 运行

使用 Python 3.12，在本目录打开终端：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run portal.py
```

macOS／Linux 使用 `.venv/bin/python`。默认地址为 http://localhost:8501。打开后进入 RQ5，通过顶部导航切换页面；两页共享国家选择。

## 数据与方法

快照日期为 **2025-04-12**，包含 **72 个国家／地区、3,600 条记录、1,962 首独立歌曲**。

数据来源：[Top Spotify Songs in 73 Countries](https://www.kaggle.com/datasets/asaniczka/top-spotify-songs-in-73-countries-daily-updated)。按完整国家榜单数最多、并列时取最新的规则选择共同日期；空国家代码不参与比较。

RQ5 按有效歌曲计算中位数和四分位数。箱线图须线采用 1.5 × IQR 规则，散点显示全部有效歌曲。RQ6 按 Spotify 歌曲 ID 匹配；Top k 重合率的分子为同时进入两国 Top k 的歌曲数，分母为 k。覆盖数是上榜国家数，不是播放量。

RQ6 点线图的纵轴固定为 0–100%，便于比较不同国家组合；点标签显示百分比，悬停可查看共同歌曲数和分母，连线用于提示榜单深度的顺序。

排名散点图按两国名次比较着色：蓝色圆点表示 A 国排名更高，橙色菱形表示 B 国排名更高，灰色方块表示同排名；点状对角线表示两国排名相等。排名 1 为最高。

`processed/` 保存快照和国家代码表；`output/` 保存数据审计、日期覆盖表和校验清单。这些文件用于启动时的数据检查。CSV 保持原始准备结果，清单仅列出本项目使用的两张数据表。

地图资源存于 `static/`，通过 Streamlit 组件一并加载，不依赖云端的 `/app/static/` 路由或外部 CDN。世界地图来源为 [Plotly world geometry](https://cdn.plot.ly/un/world_50m.json)，来源和校验值见 `static/geo/source.json`。Plotly JavaScript 文件保留原 MIT 许可声明。

## 测试与部署

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests
```

将本目录作为 GitHub 仓库根目录；保留 `.streamlit/`、`processed/`、`output/` 和 `static/`，并包含 `.gitignore` 和 `.gitattributes`。后者用于保留数据和地图资源的原始字节，避免 Git 换行转换造成校验失败。

部署时使用支持 Streamlit 的服务，入口为 `portal.py`。GitHub Pages 无法直接运行 Python 应用。
