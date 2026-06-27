# Iris 数据集花瓣与花萼分离能力分析报告

## 1. 花瓣长宽（`petal_len` vs `petal_wid`）具有极强的类间可分性  
**依据图 N**: `results\plots\plot_1782572908719.png`（按 `species` 着色的花瓣散点图）  
- 图中三类物种在花瓣长宽平面上呈现近乎线性可分的三个紧密簇：  
  - `setosa` 聚集于左下角（小花瓣），与其他两类无重叠；  
  - `versicolor` 居中，`virginica` 分布于右上区域，二者仅有轻微边界交叠；  
- **支撑数据**：`groupby_aggregate` 输出显示各物种花瓣尺寸离散度低（如 `setosa` 的 `petal_len` 标准差仅 0.174），印证簇内紧凑性。

## 2. 花萼长宽（`sepal_len` vs `sepal_wid`）存在显著类内重叠，线性分离难度更高  
**依据图 N**: `results\plots\plot_1782572908706.png`（按 `species` 着色的花萼散点图）  
- `versicolor` 与 `virginica` 在花萼维度上大面积重叠，无法通过简单直线划分；  
- `setosa` 虽相对独立，但其花萼分布范围更广（`sepal_wid` 跨度 2.3–4.4），边界模糊；  
- 对比花瓣图（`plot_1782572908719.png`）可见：**花瓣图的类间间隙远大于花萼图**，证实花瓣尺寸是更优的判别特征。

## 3. 各物种花瓣长度与宽度均呈现高度集中分布，离散趋势一致  
**依据图 N**: `results\plots\plot_1782572908698.png`（`petal_len` 分组箱线图）与 `results\plots\plot_1782572908709.png`（`petal_wid` 分组箱线图）  
- 三类物种的箱体均窄且无异常值：  
  - `setosa` 箱体最窄（`petal_len` IQR ≈ 0.3, `petal_wid` IQR ≈ 0.15），反映形态高度稳定；  
  - `virginica` 箱体略宽但仍在可控范围，与 `groupby_aggregate` 输出的标准差（`petal_len`: 0.552, `petal_wid`: 0.275）完全一致；  
- **结论**：花瓣尺寸在各类内部变异小，支持其作为鲁棒分类依据。

## 4. 花瓣尺寸跨物种梯度清晰，具备天然排序性  
**依据数据**: `groupby_aggregate` 输出的均值结果  
- `petal_len` 均值：`setosa` (1.46) < `versicolor` (4.26) < `virginica` (5.55)；  
- `petal_wid` 均值：`setosa` (0.25) < `versicolor` (1.33) < `virginica` (2.03)；  
- 两指标同步单调递增，表明花瓣发育具有跨物种一致性规律，进一步强化其判别可靠性。