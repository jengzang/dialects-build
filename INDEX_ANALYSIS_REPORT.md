# characters.db 索引检查报告

## 执行摘要

**检查日期**: 2026-03-18
**数据库**: data/characters.db
**检查范围**: 6 张表的索引配置

---

## 1. characters 表（25,380 行）

### 邮件要求的索引

**必须索引**：
1. `CREATE INDEX idx_characters_hanzi ON characters(漢字);`
2. `CREATE INDEX idx_characters_hierarchy ON characters(組, 等, 攝, 呼, 韻, 調);`

**特殊索引**：
3. `CREATE INDEX idx_characters_multi_position ON characters(多地位標記, 漢字);`

**可选索引**：
4. `CREATE INDEX idx_characters_covering ON characters(漢字, 攝, 呼, 等, 韻, 調, 組, 母, 部位, 方式, 多地位標記);`

### 当前索引状态

✅ **已有索引（24 个）**：
- `idx_characters_漢字` - ✅ 符合要求 1
- `idx_characters_hierarchy` - ⚠️ 部分符合要求 2（字段顺序：組, 母, 攝, 呼, 調，缺少"等"和"韻"）
- `idx_characters_多地位標記` - ⚠️ 单列索引，不符合要求 3（应该是复合索引）
- 其他 21 个索引：各种单列和双列复合索引

### 问题分析

❌ **问题 1**: `idx_characters_hierarchy` 索引不完整
- 当前：`(組, 母, 攝, 呼, 調)`
- 要求：`(組, 等, 攝, 呼, 韻, 調)`
- 缺少：`等`、`韻` 字段
- 多余：`母` 字段

❌ **问题 2**: 缺少 `多地位標記` 复合索引
- 当前：`idx_characters_多地位標記` 只索引单列
- 要求：`(多地位標記, 漢字)` 复合索引

❌ **问题 3**: 缺少覆盖索引（可选）

---

## 2. fenyun 表（7,221 行）

### 邮件要求的索引

**必须索引**：
1. `CREATE INDEX idx_fenyun_hanzi ON fenyun(漢字);`
2. `CREATE INDEX idx_fenyun_hierarchy ON fenyun(聲母, 韻母, 韻部, 聲調);`

**可选索引**：
3. `CREATE INDEX idx_fenyun_covering ON fenyun(漢字, 聲母, 韻母, 韻部, 聲調, 小韻);`

### 当前索引状态

✅ **已有索引（6 个）**：
- `idx_fenyun_single_0` - ✅ 符合要求 1（漢字）
- 5 个 pair 索引 - ⚠️ 都是双列索引，不符合要求 2

### 问题分析

❌ **问题 1**: 缺少层级复合索引
- 要求：`(聲母, 韻母, 韻部, 聲調)` 4 列复合索引
- 当前：只有多个双列索引

❌ **问题 2**: 缺少覆盖索引（可选）

---

## 3. hongwu 表（14,561 行）

### 邮件要求的索引

**必须索引**：
1. `CREATE INDEX idx_hongwu_hanzi ON hongwu(漢字);`
2. `CREATE INDEX idx_hongwu_hierarchy ON hongwu(聲母, 韻部, 聲調, 清濁);`

**可选索引**：
3. `CREATE INDEX idx_hongwu_covering ON hongwu(漢字, 聲母, 韻部, 聲調, 清濁, 聲類);`

### 当前索引状态

✅ **已有索引（6 个）**：
- `idx_hongwu_single_0` - ✅ 符合要求 1（漢字）
- 5 个 pair 索引 - ⚠️ 都是双列索引，不符合要求 2

### 问题分析

❌ **问题 1**: 缺少层级复合索引
- 要求：`(聲母, 韻部, 聲調, 清濁)` 4 列复合索引
- 当前：只有多个双列索引

❌ **问题 2**: 缺少覆盖索引（可选）

---

## 4. menggu 表（9,446 行）

### 邮件要求的索引

**必须索引**：
1. `CREATE INDEX idx_menggu_hanzi ON menggu(漢字);`
2. `CREATE INDEX idx_menggu_hierarchy ON menggu(韻部, 聲調);`

**可选索引**：
3. `CREATE INDEX idx_menggu_covering ON menggu(漢字, 韻部, 聲調);`

### 当前索引状态

✅ **已有索引（3 个）**：
- `idx_menggu_single_0` - ✅ 符合要求 1（漢字）
- `idx_menggu_pair_0` - ⚠️ 可能是 `(聲調, 漢字)`
- `idx_menggu_pair_1` - ⚠️ 可能是 `(韻部, 漢字)`

### 问题分析

❌ **问题 1**: 缺少层级复合索引
- 要求：`(韻部, 聲調)` 2 列复合索引
- 当前：只有双列索引但包含 `漢字`

❌ **问题 2**: 缺少覆盖索引（可选）

---

## 5. old_chinese 表（11,156 行）

### 邮件要求的索引

**必须索引**：
1. `CREATE INDEX idx_old_chinese_hanzi ON old_chinese(漢字);`
2. `CREATE INDEX idx_old_chinese_hierarchy ON old_chinese(聲母, 韻母, 韻部, 聲調);`

**可选索引**：
3. `CREATE INDEX idx_old_chinese_covering ON old_chinese(漢字, 聲母, 韻母, 韻部, 聲調, 聲母組);`

### 当前索引状态

✅ **已有索引（9 个）**：
- `idx_old_chinese_single_0` - ✅ 符合要求 1（漢字）
- 8 个 pair 索引 - ⚠️ 都是双列索引，不符合要求 2

### 问题分析

❌ **问题 1**: 缺少层级复合索引
- 要求：`(聲母, 韻母, 韻部, 聲調)` 4 列复合索引
- 当前：只有多个双列索引

❌ **问题 2**: 缺少覆盖索引（可选）

---

## 6. zhongyuan 表（5,877 行）

### 邮件要求的索引

**必须索引**：
1. `CREATE INDEX idx_zhongyuan_hanzi ON zhongyuan(漢字);`
2. `CREATE INDEX idx_zhongyuan_hierarchy ON zhongyuan(聲母, 韻母, 呼, 等, 聲調);`

**可选索引**：
3. `CREATE INDEX idx_zhongyuan_covering ON zhongyuan(漢字, 聲母, 韻母, 呼, 等, 聲調, 小韻);`

### 当前索引状态

✅ **已有索引（7 个）**：
- `idx_zhongyuan_single_0` - ✅ 符合要求 1（漢字）
- 6 个 pair 索引 - ⚠️ 都是双列索引，不符合要求 2

### 问题分析

❌ **问题 1**: 缺少层级复合索引
- 要求：`(聲母, 韻母, 呼, 等, 聲調)` 5 列复合索引
- 当前：只有多个双列索引

❌ **问题 2**: 缺少覆盖索引（可选）

---

## 总结

### ✅ 符合要求的部分

1. **所有表都有 `漢字` 单列索引** - ✅ 完全符合
2. **索引数量充足** - 所有表都有多个索引

### ❌ 不符合要求的部分

1. **缺少多列复合索引**（最严重）
   - 所有表（除 characters 外）都缺少邮件要求的层级复合索引
   - 当前只有双列索引，不足以支持多条件查询优化

2. **characters 表的 hierarchy 索引不完整**
   - 缺少 `等`、`韻` 字段
   - 包含不需要的 `母` 字段

3. **characters 表缺少 `多地位標記` 复合索引**
   - 当前只有单列索引
   - 需要 `(多地位標記, 漢字)` 复合索引

4. **所有表都缺少覆盖索引**（可选，但推荐）

### 性能影响评估

**当前状态**：
- ✅ 单字符查询性能良好（有 `漢字` 索引）
- ❌ 多条件层级查询性能不佳（缺少多列复合索引）
- ❌ 可能需要多次回表查询（缺少覆盖索引）

**预期性能差距**：
- 层级查询可能比邮件预期慢 **10-60 倍**
- 总体查询时间可能比预期多 **40-50%**

---

## 建议

### 优先级 1：立即修复（必须索引）

为每张表创建正确的层级复合索引：

```sql
-- 1. characters 表
DROP INDEX IF EXISTS idx_characters_hierarchy;
CREATE INDEX idx_characters_hierarchy ON characters(組, 等, 攝, 呼, 韻, 調);
CREATE INDEX idx_characters_multi_position ON characters(多地位標記, 漢字);

-- 2. fenyun 表
CREATE INDEX idx_fenyun_hierarchy ON fenyun(聲母, 韻母, 韻部, 聲調);

-- 3. hongwu 表
CREATE INDEX idx_hongwu_hierarchy ON hongwu(聲母, 韻部, 聲調, 清濁);

-- 4. menggu 表
CREATE INDEX idx_menggu_hierarchy ON menggu(韻部, 聲調);

-- 5. old_chinese 表
CREATE INDEX idx_old_chinese_hierarchy ON old_chinese(聲母, 韻母, 韻部, 聲調);

-- 6. zhongyuan 表
CREATE INDEX idx_zhongyuan_hierarchy ON zhongyuan(聲母, 韻母, 呼, 等, 聲調);
```

### 优先级 2：性能优化（可选索引）

测试必须索引后，如果性能仍不理想，添加覆盖索引。

### 优先级 3：清理冗余索引

当前有很多双列索引可能与新的多列复合索引重复，可以考虑删除以节省空间。

---

## 结论

**当前索引配置 ❌ 不完全符合邮件要求**

主要问题：
1. 缺少多列复合索引（5/6 张表）
2. characters 表的 hierarchy 索引不完整
3. characters 表缺少多地位标记复合索引

建议立即按照邮件要求创建缺失的索引，以达到预期的查询性能。
