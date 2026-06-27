# Iris 数据集多维度可视化分析报告

## 1. 花瓣尺寸（petal_len vs petal_wid）的物种分离性  
**图 1**: `results\plots\plot_1782571568719.png`  
- 散点图显示 `petal_len` 与 `petal_wid` 在三类物种间呈现高度线性可分性：  
  - `setosa` 聚集在左下角（花瓣短而窄）；  
  - `versicolor` 居中；  
  - `virginica` 分布于右上（花瓣长且宽），三类间边界清晰。  
- **依据**: Coder 执行 `scatter_plot(x='petal_len', y='petal_wid', hue='species')`，输出该图。

## 2. 四维特征在物种间的分布差异  
**图 2–5**: 箱线图矩阵（4张独立图）  
- `sepal_len`（图 2, `plot_1782571586858.png`）：`virginica` 中位数最高（≈6.4），`setosa` 最低（≈5.0），但三类存在明显重叠。  
- `sepal_wid`（图 3, `plot_1782571586841.png`）：`setosa` 宽度最大（中位数≈3.4），`virginica` 最小（≈3.0），重叠程度高于 `petal_len`。  
- `petal_len`（图 4, `plot_1782571586851.png`）：三类中位数依次为 1.5（setosa）、4.35（versicolor）、5.6（virginica），离散度小、间隔大，判别力最强。  
- `petal_wid`（图 5, `plot_1782571586852.png`）：与 `petal_len` 高度一致，`setosa` 显著窄于另两类（≈0.2 vs ≈1.3/2.0）。  
- **依据**: Coder 执行 4 次独立 `box_plot` 调用，分别输出对应路径的图。

## 3. 类别平衡性验证  
**图 6**: `results\plots\plot_1782571602345.png`  
- 饼图显示 `setosa`、`versicolor`、`virginica` 各占 33.3%（50/150），数据集完全平衡。  
- **依据**: Coder 执行 `pie_plot(labels=['setosa','versicolor','virginica'], values=[50,50,50])`，输出该图。

---

**结论**：花瓣尺寸（尤其 `petal_len`）是区分 Iris 三类物种最有效的单维特征；花瓣长宽组合提供最优二维线性可分性；花萼尺寸判别力较弱且重叠较多；数据集无类别偏差，适合后续建模。