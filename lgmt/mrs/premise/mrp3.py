'''
MR-P3: Irrelevant Premise Extension

this MR is special because it do not need to regenerate the nl premises
'''
import sys
from pathlib import Path
import random
import json
from typing import List, Dict, Any

# 设置UTF-8编码以支持Unicode字符（仅在未设置过时）
import io
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except (AttributeError, ValueError):
        pass  # 如果无法重设，继续使用现有配置


from lgmt.core.structure import MetamorphicRelation
from lgmt.core.structure import TestCase


class MRP3(MetamorphicRelation):
    """
    MR-P3: 无关扩展
    
    变换规则：向前提集合中添加一个逻辑上无关但不矛盾的前提
    
    无关前提的生成：
    - 采用数学公式形式，如 "1+1=2", "5*2=10" 等
    """
    
    def __init__(self):
        self.index = "MR-P3"
        self.name = "Irrelevant Extension"

    # =========================================================================
    # MR 标准接口实现
    # =========================================================================
    def source_templates(self) -> List[str]:
        """
        MR-P3 是通用的，适用于任何测试用例
        """
        return []  # 空列表表示通用

    def check_applicability_logic(self, fol: str) -> bool:
        """
        检查单个 FOL 公式是否适用于 MR-P3（MR-P3 对任何公式都适用）
        """
        return True

    def check_applicability_formula(self, formula: str) -> bool:
        """
        单个公式的适用性检查（MR-P3对所有公式都适用）
        """
        return True

    def check_applicability(self, test_case: TestCase) -> bool:
        """
        检查测试用例是否适用于MR-P3
        
        适用条件：MR-P3 对所有测试用例都适用，因为无关前提可以添加到任何前提集合中
        """
        return True

    # =========================================================================
    # 无关前提生成方法
    # =========================================================================
    def _generate_arithmetic_formula(self) -> tuple:
        """
        生成一个随机的数学公式（无关前提）
        采用复杂的形式，涉及平方、幂等操作
        
        Returns:
            tuple: (逻辑形式, 自然语言形式)
        """
        # 平方、幂等操作
        num1 = random.randint(2, 12)
        power = random.randint(2, 4)
        result = num1 ** power
        logic = f"{num1}^{power}={result}"
        text = f"{num1} to the power of {power} equals {result}."
        
        return logic, text

    def _generate_irrelevant_premise(self) -> tuple:
        """
        生成一个无关前提
        
        Returns:
            tuple: (逻辑形式, 自然语言形式)
        """
        return self._generate_arithmetic_formula()

    # =========================================================================
    # 主要变换方法
    # =========================================================================
    def transform(self, stc: TestCase) -> TestCase:
        """
        执行无关扩展变换
        
        逻辑：
        2. 生成一个无关前提（数学公式）
        3. 将其添加到前提集合末尾
        4. 保持结论不变
        5. 返回新的 TestCase
        """
        
        # 复制前提列表
        new_premises_logic = stc.premises_logic.copy()
        new_premises_text = stc.premises_text.copy()
        
        # 生成无关前提
        irrelevant_logic, irrelevant_text = self._generate_irrelevant_premise()
        
        # 添加到前提集合末尾
        new_premises_logic.append(irrelevant_logic)
        # 为新增的无关前提添加标记
        # 使用 [Added_{index}] 标记表示这是新添加的前提，index 是其在列表中的位置
        index = len(new_premises_logic) - 1  # 新前提的索引
        new_premises_text.append(irrelevant_text)
        
        # 返回新的 TestCase，结论保持不变
        return TestCase(
            premises_text=new_premises_text,
            conclusion_text=stc.conclusion_text,
            premises_logic=new_premises_logic,
            conclusion_logic=stc.conclusion_logic,
            metadata=stc.metadata.copy()  # 保留元数据
        )

