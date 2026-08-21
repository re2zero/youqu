# Pipeline B Report

## 项目
- 名称: {{project_name}}

## 覆盖率
- 元素 A（可交互控件类）: {{total}}
- 元素 B（已有名称）: {{ok}}
- 覆盖率: {{coverage}}%

## 按模块覆盖率
| 模块 | A | B | 覆盖率 | Gap 数 |
|------|---|---|--------|--------|
{% for m in modules %}
| {{ m.module }} | {{ m.total }} | {{ m.ok }} | {{ m.coverage }}% | {{ m.gaps }} |
{% endfor %}

## Gap 列表
| 类名 | 类型 | 文件 | 推断原因 |
|------|------|------|---------|
{% for g in gaps %}
| {{ g.class }} | {{ g.type }} | {{ g.file }} | {{ g.reason }} |
{% endfor %}