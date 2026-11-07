"""跨 handler 复用的共享实现。

本包用于安放原分散在各 handler 模块里、被其它 handler 直接 import 的非公开
逻辑（LLM 配置读取、物料选择、观测清洗、投递状态归一等），避免 handler 之间
互相 import 下划线函数。

约定：
- 共享函数不再依赖某个 handler 模块的模块级可变状态；
- 原 handler 模块继续 re-export 同名符号，保证既有 import 与测试不受影响；
- 需要读取原 handler 模块级符号（例如测试会 patch 的路径常量）时，使用
  ``handler_state`` 在运行时动态读取，避免拆分后 patch 失效。
"""
