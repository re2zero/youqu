# Pipeline A Report

## 项目
- 路径: {{project_path}}
- C++ 文件: {{parsed_files}}/{{total_files}}

## C++ 覆盖率
- 元素 A（可交互控件总数）: {{total}}
- 元素 B（已有名称）: {{ok}}
- 覆盖率: {{coverage}}%

## 按模块覆盖率
| 模块 | A | B | 覆盖率 | Gap 数 |
|------|---|---|--------|--------|
{% for m in modules %}
| {{ m.module }} | {{ m.total }} | {{ m.ok }} | {{ m.coverage }}% | {{ m.gaps }} |
{% endfor %}

## Gap 列表
| 变量 | 类型 | 文件 | 行号 | 缺 objectName | 缺 accessibleName |
|------|------|------|------|--------------|------------------|
{% for g in gaps %}
| {{ g.variable }} | {{ g.type }} | {{ g.source_file }} | {{ g.line }} | {{ '✓' if not g.has_object_name }} | {{ '✓' if not g.has_accessible_name }} |
{% endfor %}

{% if qml_total %}
## QML 覆盖率
- 元素 A: {{ qml_total }}
- 元素 B: {{ qml_ok }}
- 覆盖率: {{ qml_coverage }}%
{% endif %}