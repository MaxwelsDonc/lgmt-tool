# LGMT 工具开发实施规范：Workflow 3 极简重构 & 自定义 MR 动态注册（含 Z3 验真）

> **目标读者**：负责 `LGMT-Tool/` 代码开发的同学  
> **设计原则**：**极简前端 + 智能后端（Smart Backend, Minimal Frontend）**。前端绝不逼用户选输入格式、不暴露底层调试开关；同时打通“自定义 MR 动态注册 + Z3 等价性自动校验”，与 ICSE 2027 Tool Paper 的 §3.2（Listing 1）和 §4（Scenario B）完全对齐。

---

## 一、总体改动范围（涉及 4 个文件）

| 文件路径 | 核心改动任务 | 预估改动量 |
| :--- | :--- | :--- |
| `lgmt/mrs/__init__.py` & `lgmt/mrs/verifier.py`（新增） | 支持从外部 `.py` 文件或源码字符串动态加载自定义 `MetamorphicRelation` 子类，并调用 Z3 SMT 求解器验证变换前后的逻辑等价性。 | ~90 行 |
| `lgmt/core/builder.py` | 统一入口函数 `parse_and_normalize_cases(raw_input, translator, extractor)`：自动嗅探输入是 JSONL、纯自然语言段落还是 FOL 公式，无需前端指定 `input_mode`。 | ~40 行 |
| `lgmt/cli.py` | 为 `lgmt build-mgs` 和 `lgmt list-mrs` 增加 `--mr-file <path.py>` 参数（加载外部自定义 MR 并执行 Z3 校验）。 | ~25 行 |
| `lgmt/webapp.py` | 1. **重构 Tab 3（Test Custom Cases）**：砍掉 3 个子模式 Tab、Batch 队列框、Mock 下拉框和 Realize 复选框，精简为 **“同步模型栏 + 单一智能输入框 + 默认折叠的 `+ Register Custom MR` 抽屉”**；<br>2. 新增 `POST /api/register-mr` 接口。 | 净删减 ~120 行 |

---

## 二、模块实施细则

### 模块 1：自定义 MR 动态注册与 Z3 自动验真（`lgmt/mrs/`）

#### 1.1 接口要求（在 `lgmt/mrs/__init__.py` 中暴露）
新增两个公共函数，供 CLI（`--mr-file`）和 Web 端（`/api/register-mr`）共同调用：

```python
def register_mr_class(cls: type, verify_z3: bool = True) -> dict:
    """校验并注册一个 MetamorphicRelation 子类。

    步骤：
    1. 检查 issubclass(cls, MetamorphicRelation)，且能无参实例化 `mr = cls()`，
       具有非空的 `mr.index`（如 "MR-CX"）和 `mr.name`。
    2. 若 verify_z3=True，调用 `verify_mr_equivalence_with_z3(mr)`：
       - 使用内置的 5 条标准 FOL 测试样本（覆盖全称量词、蕴涵、合取/析取、否定）；
       - 对每条样本构造 TestCase，若 `mr.check_applicability(tc)` 为 True，
         执行 `follow = mr.transform(tc)`；
       - 复用 `tests/z3check.py` 的 NLTK-FOL → Z3 转换与全称闭包等价判定逻辑，
         验证 `(∧ Γ_s -> q_s) <-> (∧ Γ_f -> q_f)` 的否定在 Z3 下为 `unsat`；
       - 若发现 `sat`（不等价）或语法无法被 `LogicParser` 解析，抛出 `ValueError` 并附带反例说明。
    3. 验证通过后，将 `cls` 写入 `MR_CLASS_REGISTRY[cls.__name__] = cls`，
       将实例写入 `MR_INDEX_REGISTRY[mr.index] = mr` 并追加到 `ALL_MRS`（若同 index 已存在则替换）。
    4. 返回 {"index": mr.index, "name": mr.name, "class_name": cls.__name__, "verified_count": k}。
    """
```

```python
def load_mr_from_source(code_str: str, verify_z3: bool = True) -> list[dict]:
    """从 Python 源码字符串（或读取的 .py 文件内容）中加载所有 MetamorphicRelation 子类并注册。"""
```

> **代码复用提示**：目前 Z3 翻译器已经现成写在 `tests/z3check.py` 里，直接把 `tests/z3check.py` 移入 `lgmt/utils/z3check.py`（在 `tests/z3check.py` 里保留 `from lgmt.utils.z3check import *` 兼容现有单测），这样正式包就能直接调用 Z3 验真，无需重写！

---

### 模块 2：后端输入格式自动嗅探（`lgmt/core/builder.py` & `lgmt/webapp.py`）

前端不再传 `input_mode="form" | "unstructured" | "jsonl"`，统一传一个字符串 `raw_text`。后端 `_parse_source_cases(raw_text, translator, extractor)` 按以下规则**自动嗅探**：

1. **按行扫描非空行**：
   - **分支 A（JSONL 格式）**：如果所有非空行都以 `{` 开头，按 JSONL 逐行 `json.loads()`：
     - 若含 `premises_logic` + `conclusion_logic`：直接使用（若缺 `premises_text` 自动用公式字符串回填）；
     - 若仅含 `premises_text` + `conclusion_text`（英文或中文）：自动调用 `translator`（`NL→FOL`）合成并经 NLTK `LogicParser` 校验。
   - **分支 B（含 `->` 或 `|-` 或 `Therefore:` 的快速单题/多题文本）**：
     - 若用户直接输入了纯 FOL 或自然语言段落（不以 `{` 开头），按空行（`\n\n`）切分为多个题目块 `blocks`；
     - 对每个 `block`：
       - 如果每一行都是合法的 FOL 公式（通过 `looks_like_fol(line)` 检测，最后一行作为 `conclusion_logic`，其余行作为 `premises_logic`），直接构造纯 FOL 用例；
       - 否则，将该 `block` 作为非结构化自然语言段落，调用 `extractor` 自动拆解为 `{"premises_text": [...], "conclusion_text": "..."}`，再调用 `translator` 合成 `premises_logic` 与 `conclusion_logic`。

---

### 模块 3：Web UI 极简重构（`lgmt/webapp.py`）

#### 3.1 三个 Tab 的状态隔离（必须保持）
- 保持 `TAB_STATE[1]`（Quick Demo）、`TAB_STATE[2]`（Benchmark）、`TAB_STATE[3]`（Custom Cases）严格独立；
- 切换顶部 Tab 时，若目标 Tab 尚未运行过，下方报告区必须显示该 Tab 专属的空状态提示框（Empty State），绝不残留其他 Tab 的报告。

#### 3.2 Tab 2 与 Tab 3 共享模型配置
- 当用户在 Tab 2 输入了 `API Key`、`Base URL`、`Model Name`、`Prompting` 后，切换到 Tab 3 时通过 JS 自动同步这些输入框的值（反之亦然），避免用户填两次。

#### 3.3 Tab 3（`3. Test Custom Cases`）界面大瘦身
**删掉的内容**：
- ❌ 删掉 `Mode A: Quick Form` / `Mode B: Unstructured` / `Mode C: Batch JSONL` 三个子标签切换栏；
- ❌ 删掉 `Batch Queue` 队列管理列表与 `+ Add to Batch` / `Clear Batch` 按钮；
- ❌ 删掉 `Expected Label (True/False/Unknown)` 下拉框（紧扣论文 *No ground-truth labels required* 卖点）；
- ❌ 删掉 `Execution Mode (Real API vs Offline Mock)` 下拉框和 `LLM Logic→NL Realization` 复选框（Web 端 Tab 3 统一使用真实模型并默认开启回译）。

**保留的极简布局（仅 3 块）**：

1. **第一行：模型配置栏**（`API Key` | `Base URL` | `Model Name` | `Prompting Strategy`）
2. **第二行：统一智能输入框（One Smart Input）**
   - 标题栏左侧：`Test Cases (Paste plain text, Chinese/English sentences, FOL formulas, or JSONL — no ground-truth labels needed)`
   - 标题栏右侧（仅 2 个轻量控件）：
     - `Load Example ▾` 下拉框（含 3 个选项：`1. Plain Text — Medical & Legal (English)`、`2. 中文业务规则段落 (Chinese)`、`3. Structured JSONL (NL + FOL)`，选中即填入文本框）
     - `📂 Upload File` 按钮（支持 `.txt` / `.jsonl` 本地文件读取填入文本框）
   - 下方：1 个干净的多行 `<textarea id="c-cases" rows="6">`，默认预填 `Plain Text — Medical & Legal` 示例。
3. **第三行：MR 规则栏 + 默认折叠的 `+ Register Custom MR` 抽屉 + 运行按钮**
   - 规则勾选行：
     `MR Categories: [✓] E (Formula ×10)  [✓] S (Symbol ×2)  [✓] P (Premise ×5)  [✓] C (Conclusion ×3)`  
     右侧附带已注册的自定义 MR 复选框容器 `<span id="custom-mr-checks"></span>` 以及一个轻量按钮 **`➕ Register Custom MR`**。
   - **自定义 MR 折叠抽屉（默认隐藏 `display: none`，点击 `➕ Register Custom MR` 展开）**：
     - 预填与论文 **Listing 1** 完全一致的 15 行可运行代码模板（`MRCxDoubleNegation`）：
       ```python
       import copy
       from nltk.sem.logic import LogicParser, NegatedExpression
       from lgmt.core.structure import MetamorphicRelation, TestCase

       class MRCxDoubleNegation(MetamorphicRelation):
           def __init__(self):
               self.index = "MR-CX"
               self.name = "Double Negation (Custom)"

           def check_applicability_logic(self, fol: str) -> bool:
               return bool(fol)

           def source_templates(self) -> list[str]:
               return []

           def check_applicability(self, tc: TestCase) -> bool:
               return bool(tc.conclusion_logic)

           def transform(self, tc: TestCase) -> TestCase:
               follow = copy.deepcopy(tc)
               ast = LogicParser().parse(tc.conclusion_logic)
               follow.conclusion_logic = str(NegatedExpression(NegatedExpression(ast)))
               follow.conclusion_text = f"[Changed_conclusion] It is not the case that not ({tc.conclusion_text})"
               return follow
       ```
     - 右下角按钮：**`Verify with Z3 & Register`**（调用 `POST /api/register-mr`）：
       - 成功后显示绿色状态条：`✓ Z3 Equivalence Verified (5/5 test formulas) · Registered MR-CX: Double Negation (Custom)`；
       - 同时在上方规则勾选行自动插入并勾选 `[✓] MR-CX (Custom)`。

---

### 模块 4：CLI 同步支持 `--mr-file`（`lgmt/cli.py`）

在 `lgmt build-mgs` 和 `lgmt list-mrs` 的参数解析器中增加：
```python
p.add_argument(
    "--mr-file",
    action="append",
    default=None,
    help="Path to a Python file defining custom MetamorphicRelation subclass(es); verified with Z3 on load.",
)
```
这与论文 §3.2 Listing 1 的描述形成 100% 闭环：审稿人既可以在 Web 抽屉里一键点 `Verify with Z3 & Register`，也可以在命令行用 `--mr-file my_mr.py` 加载自定义规则。

---

## 三、验收 Checklist（同学改完后跑这 4 条命令自检）

1. **全量单测通过**：
   ```bash
   pytest -v
   ```
2. **CLI 加载外部自定义 MR 并通过 Z3 验真**：
   ```bash
   lgmt list-mrs --mr-file examples/custom_mr_example.py
   ```
3. **Web 界面三 Tab 隔离验证**：
   启动 `lgmt web --port 7860` → 在 Tab 1 点击 `Run Offline Demo` 出结果 → 点击切换到 Tab 2 和 Tab 3，确认下方只显示各自 Tab 的空状态提示，绝不残留 Tab 1 的卡片。
4. **Web 界面 Tab 3 极简流程验证**：
   在 Tab 3 点击 `➕ Register Custom MR` → 点击 `Verify with Z3 & Register` 看到绿色 `Z3 Equivalence Verified` 提示 → 用默认示例直接点 `Build MGs & Test Model` 跑出报告。
