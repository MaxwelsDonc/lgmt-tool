'''
MR-P2: Premise Duplication

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
    except AttributeError:
        pass


from lgmt.core.structure import MetamorphicRelation
from lgmt.core.structure import TestCase

# =============================================================================
# MR-P2: Premise Duplication
# =============================================================================

class MRP2(MetamorphicRelation):
    """
    MR-P2: 前提重复
    
    变换规则：从现有前提集合Γ中随机选择 n 个前提，复制并添加到前提集合中
    适用范围：至少有1个前提的测试用例
    
    理论依据：在一阶逻辑中，重复的前提不会改变推理结果
    例如：{P(a), Q(b)} ⊢ R(c) 等价于 {P(a), P(a), Q(b)} ⊢ R(c)
    
    该变换引入冗余但不添加新信息，可用于测试模型对冗余信息的鲁棒性
    
    参数：
        n_duplicates: 要复制的前提数量（默认为1）
                     - 如果 n_duplicates >= 原前提数量，则每个前提都会被复制一次
                     - 否则随机选择 n_duplicates 个不同的前提进行复制
    """
    
    def __init__(self, n_duplicates: int = 1):
        self.index = "MR-P2"
        self.name = "Premise Duplication"
        self.n_duplicates = max(1, n_duplicates)  # 至少复制1个前提

    # =========================================================================
    # MR 标准接口实现
    # =========================================================================
    def source_templates(self) -> List[str]:
        """
        MR-P2 是通用的，适用于任何有前提的测试用例
        """
        return []  # 空列表表示通用
    def check_applicability_logic(self, fol: str) -> bool:
        """
        检查单个 FOL 公式是否适用于 MR-P2（MR-P2 对任何公式都适用）
        """
        return True

    def check_applicability_formula(self, formula: str) -> bool:
        """
        单个公式的适用性检查（MR-P2不需要检查单个公式，而是检查前提数量）
        """
        return True  # 对单个公式总是返回True

    def check_applicability(self, test_case: TestCase) -> bool:
        """
        检查测试用例是否适用于MR-P2
        
        适用条件：至少有1个前提（才能进行复制）
        """
        return len(test_case.premises_logic) >= 1

    def transform(self, stc: TestCase) -> TestCase:
        """
        执行前提重复变换
        
        逻辑：
        1. 复制前提列表（逻辑形式和文本形式）
        2. 随机选择 n_duplicates 个前提（如果前提总数少于 n_duplicates，则选择全部）
        3. 将选中的前提复制并添加到列表末尾
        4. 保持结论不变
        5. 返回新的TestCase
        """
        # 检查是否适用
        if not self.check_applicability(stc):
            print(f"[Warning] MR-P2 not applicable: need at least 1 premise, got {len(stc.premises_logic)}")
            return stc
        
        # 复制前提列表
        new_premises_logic = stc.premises_logic.copy()
        new_premises_text = stc.premises_text.copy()
        
        # 确定实际要复制的数量
        actual_n = min(self.n_duplicates, len(new_premises_logic))
        
        # 随机选择 actual_n 个不同的索引进行复制
        if actual_n >= len(new_premises_logic):
            # 如果要复制的数量 >= 前提总数，复制所有前提
            duplicate_indices = list(range(len(new_premises_logic)))
        else:
            # 否则随机选择 actual_n 个不同的前提
            duplicate_indices = random.sample(range(len(new_premises_logic)), actual_n)
        
        # 复制选中的前提并添加到列表末尾
        for idx in duplicate_indices:
            new_premises_logic.append(new_premises_logic[idx])
            # 为复制的前提添加 [Changed_{original_index}] 标记
            new_premises_text.append(new_premises_text[idx])
        
        # 返回新的TestCase，结论保持不变
        return TestCase(
            premises_text=new_premises_text,
            conclusion_text=stc.conclusion_text,
            premises_logic=new_premises_logic,
            conclusion_logic=stc.conclusion_logic,
            metadata=stc.metadata.copy()  # 保留元数据
        )
