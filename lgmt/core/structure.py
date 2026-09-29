"""
这个文件是用来定义重要的结构体，例如：
- 测试用例 test case
- source-follow pairs (MG)
- 蜕变关系 (MR)
"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from abc import ABC, abstractmethod
from enum import Enum
import re
from colorama import Fore, Style

#===========================================
# 测试用例 test case
#===========================================
@dataclass
class TestCase:
    """
    对应论文中的 (Γ, q) 结构
    """    
    # 核心逻辑部分 (Logic Level)
    # 对应论文：Γ is a finite set of first-order formulas 
    premises_logic: List[str]  # 例如 ["∀x(P(x) -> Q(x))", "P(a)"]
    # 对应论文：q is the conclusion formula 
    conclusion_logic: str      # 例如 "Q(a)"
    
    # 自然语言部分 (Prompt Level - 喂给模型的)
    premises_text: List[str]   # 例如 ["All humans are mortal.", "Socrates is human."]
    conclusion_text: str       # 例如 "Socrates is mortal."
    
    # 修改为 field，确保每次调用的是一个新的空字典
    metadata: Dict[str, Any] = field(default_factory=dict)

    def display(self) -> None:
        """在控制台打印所有信息"""
        print("=" * 50)
        print("\n逻辑形式 (Logic Level):")
        print("  Premises Logic:")
        for i, premise in enumerate(self.premises_logic, 1):
            print(f"    {i}. {premise}")
        print(f"  Conclusion Logic: {self.conclusion_logic}")
        
        print("\n自然语言形式 (Natural Language):")
        print("  Premises Text:")
        for i, premise in enumerate(self.premises_text, 1):
            print(f"    {i}. {premise}")
        print(f"  Conclusion Text: {self.conclusion_text}")
        
        print("\n元数据 (Metadata):")
        if self.metadata:
            for key, value in self.metadata.items():
                print(f"  {key}: {value}")
        else:
            print("  (无元数据)")
        print("=" * 50)
    

#===========================================
#  Metamorphic Groups
#===========================================
@dataclass
class MetamorphicGroups:
    """
    记录一次 MR 变换的结果：源用例 -> 新用例
    对应论文公式: (Γ, q) => (Γ', q') [cite: 115]
    """
    source_case: TestCase
    followup_case: TestCase
    
    # 记录是用哪个 MR 变的，例如 "MR-E1.2 (Negation Normalization)" [cite: 215]
    mr_name: str 
    # 修改为 field，确保每次调用的是一个新的空字典
    metadata: Dict[str, Any] = field(default_factory=dict)

    def display(self) -> None:
        """在控制台打印所有信息"""
        print("=" * 50)
        print("\nMR 变换名称:")
        print(f" {self.mr_name}")
        print("=" * 50)
    
        print("\n🔧 源用例 (Source Test Case):")
        self.source_case.display()
        
        print("\n🔧 衍生用例 (Follow-up Test Case):")
        self.followup_case.display()
        
        print("\n元数据 (Metadata):")
        if self.metadata:
            for key, value in self.metadata.items():
                print(f"  {key}: {value}")
        else:
            print("  (无元数据)")
        print("=" * 50)
        
#===========================================
# 蜕变关系 (MR)
#===========================================

class MetamorphicRelation(ABC):
    """
    所有 MR 的基类
    """
    index: str  
    name: str   
    @abstractmethod
    def check_applicability_logic(self, fol: str) -> bool:
        """
        判断这数据能不能用这个 MR。
        """
        return False

    @abstractmethod
    def source_templates(self) -> List[str]:
        """
        【关键属性】
        返回该 MR 适用的 Source Case 模板列表。
        - 如果返回 []: 表示该 MR 适用于任何逻辑结构 (Universal)。
        """
        return []  # 默认为空，表示通用

    @abstractmethod
    def check_applicability(self,test_case: TestCase) -> bool:
        """
        判断这数据能不能用这个 MR。
        """
        return False

    @abstractmethod
    def transform(self, source_case: TestCase) -> TestCase:
        """
        核心方法：输入一个 Source Case，返回一个或多个 Follow-up Cases。
        对应论文公式: (Γ, q) => (Γ', q')
        """
        pass

    