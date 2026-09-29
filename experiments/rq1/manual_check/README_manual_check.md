# RQ1 Manual Check 标注说明

## 1. 目录说明
请确保你拿到并保留以下目录结构：

- `experiments/rq1/manual_check/check_tool/`
- `experiments/rq1/manual_check/check_data/`
- `experiments/rq1/manual_check/problem_data/`

说明：

- `check_data` 是待标注样本（已按模型准备好）
- `check_tool` 是标注工具
- `problem_data` 保存标注为问题（`problem`）的样本

## 2. 环境要求
- Python 3.9+（推荐 3.10/3.11/3.12）
- 不需要额外安装第三方包（工具仅使用 Python 标准库）

验证：

```bash
python3 --version
```

## 3. 启动标注工具
在项目根目录运行（每位标注者使用自己的名字）：

```bash
python3 experiments/rq1/manual_check/check_tool/app.py --model chatgpt --annotator your_name --port 8765
```

浏览器打开：

- `http://127.0.0.1:8765`

## 4. 支持的模型
`--model` 可选：

- `chatgpt`
- `chatgpt_reasoner`
- `claude`
- `deepseek`
- `deepseek_reasoner`
- `llama`

切换模型时，停止当前进程后重新启动即可。

示例：

```bash
python3 experiments/rq1/manual_check/check_tool/app.py --model deepseek --annotator your_name --port 8765
```

## 5. 标注规则
页面只展示 source/follow-up 中**发生变化**的部分，并展示：

- FOL
- Natural Language

只需要二分类：

- `Mark OK`
- `Mark Problem`

可选：

- 在 note 中填写问题说明（推荐简短描述）

## 6. 保存规则（重要）
- 只保存 `problem` 样本
- 输出文件路径：
  - `experiments/rq1/manual_check/problem_data/<model>/<annotator>.jsonl`
- 如果某模型下没有任何 `problem`，该文件不会存在（这是正常的）

## 7. 多人协作规范
- 每人必须使用唯一 `--annotator` 名称（如 `alice`、`bob`）
- 不要多人共用同一个 `annotator`
- 建议一次只标一个模型，标完后再切换

## 8. 常见问题
1. 端口被占用

换端口运行，例如：

```bash
python3 experiments/rq1/manual_check/check_tool/app.py --model chatgpt --annotator your_name --port 8766
```

2. 提示找不到样本文件

确认文件存在：

- `experiments/rq1/manual_check/check_data/<model>/sampled_100_seed42.jsonl`

3. 页面打不开

检查：

- 命令行是否有报错
- 是否访问了 `http://127.0.0.1:<port>`

## 9. 提交结果
标注完成后，仅需提交你自己的结果文件：

- `experiments/rq1/manual_check/problem_data/<model>/<annotator>.jsonl`

