'''
MR-P4: Premise Fusion
'''
import sys
from pathlib import Path
import random
import json
from typing import List, Dict, Any

# 设置UTF-8编码以支持Unicode字符
import io
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass


from lgmt.core.structure import MetamorphicRelation
from lgmt.core.structure import TestCase

# =============================================================================
# MR-P4: Premise Fusion
# =============================================================================

class MRP4(MetamorphicRelation):
    """
    MR-P4: 前提融合
    {P(a), Q(b)} ⊢ R(c) 变换为 {P(a) ∧ Q(b)} ⊢ R(c)
    - 删除被融合的两个原前提
    - 只保留新的合取前提
    """
    
    def __init__(self):
        self.index = "MR-P4"
        self.name = "Premise Fusion"

    # =========================================================================
    # MR 标准接口实现
    # =========================================================================
    def source_templates(self) -> List[str]:
        """
        MR-P4 是通用的，适用于任何有多个前提的测试用例
        """
        return []  # 空列表表示通用

    def check_applicability_logic(self, fol: str) -> bool:
        """
        检查单个 FOL 公式是否适用于 MR-P4（MR-P4 对任何公式都适用）
        """
        return True

    def check_applicability_formula(self, formula: str) -> bool:
        """
        单个公式的适用性检查
        """
        return True

    def check_applicability(self, test_case: TestCase) -> bool:
        """
        检查测试用例是否适用于MR-P4
        
        适用条件：至少有2个前提（才能进行融合）
        """
        return len(test_case.premises_logic) >= 2

    # =========================================================================
    # 前提融合方法
    # =========================================================================
    def _fuse_premises(self, premise1_logic: str, premise2_logic: str,
                      premise1_text: str, premise2_text: str) -> tuple:
        """
        将两个前提融合成一个合取前提
        
        Args:
            premise1_logic: 第一个前提的逻辑形式
            premise2_logic: 第二个前提的逻辑形式
            premise1_text: 第一个前提的文本形式
            premise2_text: 第二个前提的文本形式
        
        Returns:
            tuple: (融合后逻辑形式, 融合后文本形式)
        """
        # 逻辑形式：使用 ∧ 连接（或使用 & 或 AND）
        # 为了简洁，使用 ∧ 符号
        fused_logic = f"({premise1_logic}) & ({premise2_logic})"
        
        # 文本形式：使用自然语言表达合取关系
        fused_text = f"Both {premise1_text[0].lower()}{premise1_text[1:].rstrip('.')} and {premise2_text[0].lower()}{premise2_text[1:].rstrip('.')}."
        
        return fused_logic, fused_text

    # =========================================================================
    # 主要变换方法
    # =========================================================================
    def transform(self, stc: TestCase) -> TestCase:
        """
        执行前提融合变换
        
        逻辑：
        1. 检查是否适用（至少2个前提）
        2. 随机选择两个不同的前提索引
        3. 将这两个前提融合成合取形式
        4. 删除原有的两个前提
        5. 将融合后的前提添加到前提集合中
        6. 保持结论不变
        7. 返回新的 TestCase
        """
        # 检查适用性
        if not self.check_applicability(stc):
            print(f"[Warning] MR-P4 not applicable: need at least 2 premises, got {len(stc.premises_logic)}")
            return stc
        
        # 复制前提列表
        new_premises_logic = stc.premises_logic.copy()
        new_premises_text = stc.premises_text.copy()
        
        # 随机选择两个不同的前提索引
        indices = random.sample(range(len(stc.premises_logic)), 2)
        # 按从大到小排序索引
        idx1, idx2 = sorted(indices, reverse=True)
        
        # 获取选中的两个前提
        premise1_logic = stc.premises_logic[min(indices)]
        premise2_logic = stc.premises_logic[max(indices)]
        premise1_text = stc.premises_text[min(indices)]
        premise2_text = stc.premises_text[max(indices)]
        
        # 融合两个前提
        fused_logic, fused_text = self._fuse_premises(
            premise1_logic, premise2_logic,
            premise1_text, premise2_text
        )
        
        # 标记两个被融合的前提索引
        fused_text = f"[Changed_{min(indices)}][Changed_{max(indices)}] {fused_text}"
        
        # 删除原有的两个前提（从大索引开始删除，避免索引错乱）
        del new_premises_logic[idx1]
        del new_premises_logic[idx2]
        del new_premises_text[idx1]
        del new_premises_text[idx2]
        
        # 将融合后的前提添加到集合末尾
        new_premises_logic.append(fused_logic)
        new_premises_text.append(fused_text)
        
        # 返回新的 TestCase，结论保持不变
        return TestCase(
            premises_text=new_premises_text,
            conclusion_text=stc.conclusion_text,
            premises_logic=new_premises_logic,
            conclusion_logic=stc.conclusion_logic,
            metadata=stc.metadata.copy()  # 保留元数据
        )
