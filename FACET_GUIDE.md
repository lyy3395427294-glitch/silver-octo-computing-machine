# NX 小平面体（Facet Body）建模手册 — DC2606 本机实测

日期：2026-10-24　　试验件：`变速箱上盖3-20.prt`、`变速箱下盖.prt`、`3_4_flange_1.stl`
执行方式：`run_journal.exe` + NXOpen Python（一次调用一个 NX 会话）
所有"✔/✘"都在本机 v2606 实跑过，带耗时；没跑过的一律写"未验证"。

---

## 0. 一句话结论

- **小平面体只是数据底座，能拿去建模的是它转出来的"收敛体"（convergent body）**。
- 本机已跑通：`STL → 小平面体 → 减面/光顺 → 转收敛实体 → 保存`，万级面片 0.1 s 一步。
- **十万级以上、来源不明的扫描网格会卡住**：81.9 万面片的那块网格，减面（50%/90%）无变化，转收敛体报错（见 §6）。
- "网格 → 精确平面/圆柱"（识别图元、用面替换网格）这两步必须交互选面片，本次**未**脚本化，只把 API 位置和限制记下来（§7）。

---

## 1. 两个 prt 里到底是什么（实测）

| 项目 | 变速箱上盖3-20.prt | 变速箱下盖.prt |
| --- | --- | --- |
| 特征数 | **452** | **351** |
| 实体 / 片体 | 8 实体 + 4 片体 | 9 实体 |
| 小平面体个数 | 12 | 10 |
| 其中**独立**网格（无关联实体） | 1 个：**819,878** 三角形 | 1 个：**680,822** 三角形 |
| 该网格面积 / 体积 | 13,868.7 mm² / 23,647.3 mm³ | 12,004.5 mm² / 18,813.6 mm³ |
| 其余小平面体 | 11 个，全部挂在实体上（JT 显示网格，2–4 级 LOD） | 9 个，同上 |
| 单位 | mm | mm |

结论：**这两个文件是完整的参数化模型，不是扫描件**（特征树里全是 SKETCH / EXTRUDE / DRAFT / CHAMFER / REPLACE_FACE）。每个文件里额外挂着一块"野"扫描网格，正好可以当小平面体素材。

网格密度换算：面积 / 面片数 ≈ 0.0169 mm²/面 → 平均边长 ≈ **0.2 mm**（标准的手持扫描精度）。

> 判据：`FacetedBody.AssociatedBody` 为空 = 独立网格；不为空 = 某个实体/片体的显示网格。两者能做的事完全不同。

---

## 2. 三层数据模型

```
part.FacetedBodies  (FacetedBodyCollection)   -> FacetedBody    网格本身（三角形）
part.Bodies         (BodyCollection)          -> Body           实体 / 片体 / 收敛体
part.Bodies.FacetModelingCollection           -> 各种"建模级"创建器
```

判定代码（`journal/inspect_facet.py` 的简化版）：

```python
import NXOpen
import NXOpen.Facet                      # 注意：不 import 子模块，NXOpen.Facet 不存在

part = session.Parts.Open(path)[0]
for f in part.FacetedBodies:             # 不能 f.ToArray()，用 list()
    print(f.Tag, f.GetNumberOfFacets(0), f.NumberOfFaces,
          f.NumberOfLevelsOfDetail, f.SurfaceArea, f.Volume,
          f.AssociatedBody, f.IsAssemblyLevel)

for b in part.Bodies:
    print(b.Tag, b.IsSolidBody, b.IsSheetBody, b.IsConvergentBody)
    if b.IsConvergentBody:
        print(" facets:", b.GetNumberOfFacets())
```

要点：

- `FacetedBody.NumberOfFaces` 对"直接构造"的网格等于三角形数（没有面拓扑）；JT 网格才有真正的 face。
- JT 网格有 LOD（`GetNumberOfFacets(i)` 逐级变小），NX 网格通常 `1` 级。
- `Body.GetNumberOfFacets()` 只对收敛体有效；对普通实体调用会抛 `Function expects a facet topology...`（实测）。

---

## 3. 创建器在哪个集合（最容易踩的坑）

| 操作 | 创建器 | 挂在谁身上 |
| --- | --- | --- |
| STL / 网格导入 | `CreateSTLImportBuilder` | `part.FacetedBodies` |
| 减面 | `CreateDecimateFacetBodyBuilder` | `part.FacetedBodies` |
| 光顺 | `CreateSmoothFacetBodyBuilder` | `part.FacetedBodies` |
| 缝合 / 合并 / 桥接 / 剪裁 / 细分 / 补洞 / 包裹 | `CreateSewFacetBodyBuilder` 等 | `part.FacetedBodies` |
| **转收敛体** | `CreateConvertFacetBodyBuilder` | `part.FacetedBodies.FacetModelingCollection` |
| **清理修补** | `CreateCleanupFacetBodyBuilder` | 同上 |
| **识别图元**（平面/圆柱/圆锥/球） | `CreateDetectPrimitivesBuilder` | 同上 |
| **用面替换网格** | `CreateReplaceMeshWithFaceBuilder` | 同上 |

选错集合的报错长这样（实测）：
`AttributeError: 'NXOpen.Facet.FacetModelingCollection' object has no attribute 'CreateDecimateFacetBodyBuilder'`

---

## 4. 配方（全部本机跑过）

### 4.1 STL → 小平面体，三种形态任选

```python
import NXOpen, NXOpen.Facet
F = NXOpen.Facet

b = part.FacetedBodies.CreateSTLImportBuilder()
b.File = r"...\3_4_flange_1.stl"
b.STLFileUnits = F.STLImportBuilder.STLFileUnitsTypes.Millimeters
b.FacetBodyType = F.STLImportBuilder.FacetBodyTypes.Psm   # Psm / Nx / Jt
b.Commit(); b.Destroy()
```

实测差异（同一份 10,328 面片的法兰 STL）：

| FacetBodyType | 结果 | 适合 |
| --- | --- | --- |
| `Psm` | **直接得到收敛实体**（`part.Bodies` 里 1 个 solid+convergent，10,328 面）+ 它的显示网格 | 马上要布尔/测量/装配 |
| `Nx` | 只有小平面体（`part.Bodies` 为空），可在需要时再转收敛体 | 先清理/减面再转 |
| `Jt` | JT 网格（多 LOD） | 轻量查看 |

### 4.2 减面

```python
b = part.FacetedBodies.CreateDecimateFacetBodyBuilder()
b.FacetBodies.Add(facet_body)          # 用 FacetBodies，不是 Bodies
b.DecimateMethod = F.DecimateFacetBodyBuilder.DecimateMethodType.Percentage
b.Percentage = 50.0                    # "减少 50%"，不是"保留 50%"
b.Commit(); b.Destroy()
```

实测：10,328 → **5,164**（0.1 s），**就地修改，不产生新对象**（Tag 不变）。

### 4.3 光顺

```python
b = part.FacetedBodies.CreateSmoothFacetBodyBuilder()
b.Bodies.Add(facet_body)               # 2606 里 .FacetBodies 是 None，必须用 .Bodies
b.NumberOfIterations = 2
b.SmoothFactor = 0.3
b.Commit(); b.Destroy()
```

### 4.4 清理修补

```python
b = part.FacetedBodies.FacetModelingCollection.CreateCleanupFacetBodyBuilder()
b.InputBodies.Add(facet_body)
b.SetAllOptionsToRepair()              # 或 SetAllOptionsToAnalyze()
b.Commit(); b.Destroy()
```

实测：81.9 万面片 **27.9 s**，不产生新对象。

### 4.5 转收敛体

```python
b = part.FacetedBodies.FacetModelingCollection.CreateConvertFacetBodyBuilder()
b.FacetedBodiesToConvert.Add(facet_body)
b.OutputType = F.ConvertFacetBodyBuilder.OutputTypes.ConvergentBody
b.OriginalBodyOption = F.ConvertFacetBodyBuilder.OriginalBodyOptions.Keep
b.CleanUp = True
b.Commit(); b.Destroy()
```

实测：10,328 面片的 NX / JT 网格都成功（0.1 s），`part.Bodies` 里出现 `solid=True, convergent=True` 的实体。

### 4.6 保存

`Parts.FileNew()` 里如果给了 `NewFileName`，**文件当场就建出来了**，之后 `SaveAs` 同路径会报 `File already exists`。用：

```python
part.Save(NXOpen.BasePart.SaveComponents.TrueValue,
          NXOpen.BasePart.CloseAfterSave.FalseValue)
```

---

## 5. 能力矩阵（实测）

| 输入 | 减面 | 光顺 | 转收敛体 |
| --- | --- | --- | --- |
| STL 导入 `Nx`，10,328 面 | ✔ 10,328→5,164 | ✔ | ✔ solid+convergent |
| STL 导入 `Jt`，10,328 面 | 未测 | 未测 | ✔ solid+convergent |
| STL 导入 `Psm` 的显示网格 | ✔ 但只是**显示网格**变（实体仍 10,328 面） | 未测 | ✘ `not a valid faceted model`（它已经是收敛体，没有"再转"这回事） |
| 上盖独立网格 819,878 面 | ✘ 50%、90% 都无变化 | 未测 | ✘ `not a valid faceted model` |

---

## 6. 大规模网格的边界（实测结论）

上盖那块独立网格的属性：`IsAssemblyLevel=False`、`AssociatedBody=None`、`LOD=1`、`NumberOfFaces=819,878`、`IsBlanked=False`、`Layer=2`。

- 减面：`Commit()` 正常返回，**面数不变**（50% 用 5.4 s、90% 用 2.9 s）。
- 转收敛体：6.5 s 后抛 `NXException: The object supplied was not a valid faceted model`。
- 排除项：不是隐藏/图层问题（已 Unblank、图层 2 可见），不是 API 用法问题（同一套代码在 10,328 面片上 0.1 s 成功）。

**建议路径**：80 万面片先降到 **10 万级**再进 NX（MeshLab / Open3D 减面，或 CloudCompare 重采样），或者直接以 `Psm` 方式重新导入 STL，一步拿到收敛实体。

---

## 7. 与点云逆向流水线的衔接（对应关系 + 现状）

| 流水线里的步骤（Python/RANSAC） | NX 里的对应件 | 现状 |
| --- | --- | --- |
| 平面/圆柱拟合、区域生长 | `CreateDetectPrimitivesBuilder`（按 平面/圆柱/圆锥/球/过渡/其它 着色） | API 已定位；需要 facet 选择集，未跑通 |
| 拟合面 → 重建精确面 | `CreateReplaceMeshWithFaceBuilder`（Plane/Cylinder/Cone/Sphere + 平行/共线/共面/同心约束） | API 已定位；需要选网格区域，未跑通 |
| 网格 → 点云采样 | 无 NX 侧 API，走 Open3D `sample_points_uniformly` | 未做 |
| prt → STL 给外部 | `DexManager.CreateStlCreator()` | ✘ 本机 `Commit()` 崩：`Internal error: memory access violation`；`ExportSelectionBlock` 为 `None` |

也就是说：**"NX 自带 RANSAC"这条路要交互选面片，暂时不是脚本能替代的**；批量逆向仍然走"STL/点云 → Python 拟合 → CSV → NX 重建"那条已跑通的链路（见 `reverse/REPORT.md`）。

---

## 8. 陷阱清单（全是本机踩过的）

1. `import NXOpen` **不会**带出子模块：先 `import NXOpen.Facet`，否则 `module 'NXOpen' has no attribute 'Facet'`。
2. `FacetedBodyCollection` 没有 `ToArray()`，用 `list(part.FacetedBodies)`。
3. `SmoothFacetBodyBuilder.FacetBodies` 在 2606 返回 `None` → 用 `.Bodies`（否则 `'NoneType' object has no attribute 'Add'`）。
4. 减面的创建器在 `part.FacetedBodies` 上，**不在** `FacetModelingCollection`。
5. 对"收敛体的显示网格"调 Convert 必然报 `not a valid faceted model`。
6. `FileNew(NewFileName=...)` 已落盘：`SaveAs` 同路径报 `File already exists`；同一会话里重复 `Parts.Open` 同一路径也报这个。
7. **STEP(AP242) 导不出小平面体/收敛体**：显式给了 `step242ug.def` 也只写出 2,204 B、1 个 `CARTESIAN_POINT` 的空文件。网格交付用 STL / JT。
8. 开放网格的 `FacetedBody.Volume` 偏小（法兰 3/4 件：网格 57,297 mm³ vs 参数模型 62,882 mm³），别当真实体积用。
9. 一次 NX 会话 40 s–2 min，占一个 license；不要并发跑 journal。

---

## 9. 复现命令与产物

```powershell
$rj = "E:\Program Files\Siemens\Designcenter2606\NXBIN\run_journal.exe"
$d  = "E:\deepseekharness\nx-workspace\facet"

# 1) 看两个 prt 里的小平面体
& $rj "$d\journal\inspect_facet.py" -args "$d\out\inspect_both.json" `
  "C:\Users\33954\Desktop\变速箱上盖3-20.prt" "C:\Users\33954\Desktop\变速箱下盖.prt"

# 2) STL -> 小平面体 -> 减面 -> 光顺 -> 转收敛体 -> 存盘
& $rj "$d\journal\facet_from_stl.py" -args `
  "E:\deepseekharness\Reverse-engineering-parametric-CAD\3_4_flange_1.stl" `
  "$d\out\facet_flange.prt" "$d\out\facet_flange.step" "$d\out\facet_from_stl.json" 50

# 3) 三种导入形态的能力对照（会生成 truth_nx/jt/psm.prt）
& $rj "$d\journal\facet_truth.py" -args `
  "E:\deepseekharness\Reverse-engineering-parametric-CAD\3_4_flange_1.stl" "$d\out" "$d\out\facet_truth.json"
```

产物：

| 文件 | 内容 |
| --- | --- |
| `out\inspect_both.json` | 两个 prt 的实体/网格/特征清单（12 个网格逐项） |
| `out\facet_truth.json` | 三种导入形态 × 减面/转收敛 的实测结果 |
| `out\probe_gear.json`、`out\unblank.json` | 81.9 万面片网格的边界测试 |
| `out\facet_variants2.prt` | 一个 part 里同时有 Psm/Nx/Jt 三种网格 + 1 个收敛实体，可直接打开对比 |
| `out\truth_nx.prt` / `truth_jt.prt` / `truth_psm.prt` | 三种形态各自的干净样例 |