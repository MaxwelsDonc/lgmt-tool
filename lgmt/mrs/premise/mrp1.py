'''
MR-P1: Premise Reordering

this MR is special because it do not need to regenerate the nl premises
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
    except (AttributeError, ValueError):
        pass  # 如果无法重设，继续使用现有配置


from lgmt.core.structure import MetamorphicRelation
from lgmt.core.structure import TestCase

# =============================================================================
# MR-P1: Premise Reordering
# =============================================================================

class MRP1(MetamorphicRelation):
    """
    MR-P1: 前提重排序
    
    变换规则：随机打乱前提的顺序，但保持结论不变
    适用范围：至少有2个前提的测试用例
    
    理论依据：在一阶逻辑中，前提的顺序不影响推理结果
    例如：{P(a), Q(b)} ⊢ R(c) 等价于 {Q(b), P(a)} ⊢ R(c)
    """
    
    def __init__(self):
        self.index = "MR-P1"
        self.name = "Premise Reordering"
    # =========================================================================
    # MR 标准接口实现
    # =========================================================================
    def source_templates(self) -> List[str]:
        """
        MR-P1 是通用的，适用于任何有多个前提的测试用例
        """
        return []  #通用

    def check_applicability_logic(self, fol: str) -> bool:
        """
        检查单个 FOL 公式是否适用于 MR-P1（MR-P1 对任何公式都适用）
        """
        return True

    def check_applicability_formula(self, formula: str) -> bool:
        """
        单个公式的适用性检查（MR-P1不需要检查单个公式，而是检查前提数量）
        """
        return True  # 对单个公式总是返回True

    def check_applicability(self, test_case: TestCase) -> bool:
        """
        检查测试用例是否适用于MR-P1
        
        适用条件：至少有2个前提（否则无法重排序）
        """
        return len(test_case.premises_logic) >= 2

    def transform(self, stc: TestCase) -> TestCase:
        """
        执行前提重排序变换
        
        逻辑：
        1. 复制前提列表（逻辑形式和文本形式）
        2. 使用random.shuffle打乱顺序
        3. 保持结论不变
        4. 返回新的TestCase
        """
        # 检查是否适用
        if not self.check_applicability(stc):
            print(f"[Warning] MR-P1 not applicable: need at least 2 premises, got {len(stc.premises_logic)}")
            return stc
        
        # 复制前提列表
        new_premises_logic = stc.premises_logic.copy()
        new_premises_text = stc.premises_text.copy()
        original_logic = new_premises_logic.copy()
        
        # 创建索引列表并打乱
        indices = list(range(len(new_premises_logic)))
        max_attempts = 20  # 避免极端情况下的无限循环
        attempts = 0
        while attempts < max_attempts:
            random.shuffle(indices)
            # 如果打乱后顺序与原顺序相同，则继续尝试
            if [new_premises_logic[i] for i in indices] != original_logic:
                break
            attempts += 1
        
        # 根据打乱的索引重新排列前提
        new_premises_logic = [new_premises_logic[i] for i in indices]
        # 只为位置发生改变的前提添加 [Changed_{original_index}] 标记
        new_premises_text = [new_premises_text[i] for i in indices]
        
        # new_premises_text = [
        #     f"[Changed_{indices[new_pos]}] {new_premises_text[indices[new_pos]]}" 
        #     if indices[new_pos] != new_pos  # 只标记新位置与原位置不同的前提
        #     else new_premises_text[indices[new_pos]]
        #     for new_pos in range(len(indices))
        # ]
        
        # 返回新的TestCase，结论保持不变
        return TestCase(
            premises_text=new_premises_text,
            conclusion_text=stc.conclusion_text,
            premises_logic=new_premises_logic,
            conclusion_logic=stc.conclusion_logic,
            metadata=stc.metadata.copy()
        )
