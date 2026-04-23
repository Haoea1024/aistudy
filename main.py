# -*- coding: utf-8 -*-
import os
import json
import tomli
import re
from PyPDF2 import PdfReader
from openai import OpenAI

os.environ["PYTHONUTF8"] = "1"


def calc_bmi(height_cm, weight_kg):
    """计算BMI"""
    try:
        h = float(height_cm) if height_cm else None
        w = float(weight_kg) if weight_kg else None
        if h and w and h > 0:
            return round(w / ((h / 100) ** 2), 1)
        return None
    except:
        return None


# -------------------- 1. 生命体征规则 --------------------
def process_vitals(data):
    """处理基础生命体征和体格检查数据"""
    result = data.copy()

    result["bmi"] = calc_bmi(result.get("height"), result.get("weight"))

    internal_text = result.get("internal_medicine_exam", "")
    if internal_text:
        has_rales = "湿啰音" in internal_text or "干啰音" in internal_text
        negation_patterns = [
            r"无.*啰音", r"未见.*啰音", r"未闻及.*啰音",
            r"啰音.*未见", r"无异常.*啰音", r"啰音消失"
        ]
        has_rales_negation = any(re.search(pattern, internal_text) for pattern in negation_patterns)
        result["lung_abnormal_positive"] = has_rales and not has_rales_negation
    else:
        result["lung_abnormal_positive"] = False

    breast_nodule = result.get("breast_nodule", False)
    if breast_nodule:
        size = result.get("breast_nodule_size", "")
        props = result.get("breast_nodule_properties", "")
        if size and "×" in size:
            parts = re.findall(r'([\d.]+)', size)
            if parts:
                max_cm = max(float(p) for p in parts)
                result["breast_nodule_max_mm"] = round(max_cm * 10, 1)
        result["breast_nodule_positive"] = True
        high_risk_keywords = ["质硬", "边界不清", "活动度差", "形态不规则"]
        risk_count = sum(1 for kw in high_risk_keywords if kw in props)
        result["breast_nodule_high_risk"] = risk_count >= 2
    else:
        result["breast_nodule_positive"] = False
        result["breast_nodule_high_risk"] = False

    return result


# -------------------- 2. 实验室检查规则 --------------------
def glucose_judge(value):
    try:
        v = float(value) if value else None
        if v is None:
            return "unknown"
        if v >= 7.0:
            return "diabetes"
        if v >= 6.1:
            return "impaired"
        return "normal"
    except:
        return "unknown"


def urine_protein_mapping(qualitative):
    mapping = {
        "++++": "4+", "+++": "3+", "++": "2+",
        "+": "1+", "+/-": "trace", "-": "negative"
    }
    return mapping.get(qualitative, qualitative)


def tbs_mapping(tbs_result):
    mapping = {
        "ASC-US": {"code": "ASC-US", "level": 1, "description": "意义不明确的非典型鳞状细胞"},
        "ASC-H": {"code": "ASC-H", "level": 2, "description": "不除外高级别病变的非典型鳞状细胞"},
        "LSIL": {"code": "LSIL", "level": 2, "description": "低度鳞状上皮内病变"},
        "HSIL": {"code": "HSIL", "level": 3, "description": "高度鳞状上皮内病变"},
        "AGC": {"code": "AGC", "level": 2, "description": "非典型腺细胞"}
    }
    return mapping.get(tbs_result, {"code": tbs_result, "level": 0, "description": "未知"})


def process_lab(data):
    result = data.copy()
    result["glucose_judge"] = glucose_judge(result.get("fasting_glucose"))
    result["glucose_judge_cn"] = {
        "normal": "正常", "impaired": "空腹血糖受损（糖尿病前期）",
        "diabetes": "糖尿病", "unknown": "未知"
    }.get(result["glucose_judge"], "未知")

    urine_qual = result.get("urine_protein_qualitative")
    if urine_qual:
        result["urine_protein_standardized"] = urine_protein_mapping(urine_qual)

    tbs = result.get("tbs_result")
    if tbs:
        result["tbs_structured"] = tbs_mapping(tbs)

    tg = result.get("triglyceride")
    if tg:
        try:
            if float(tg) > 2.3:
                result["triglyceride_judge"] = "high"
            elif float(tg) > 1.7:
                result["triglyceride_judge"] = "borderline"
            else:
                result["triglyceride_judge"] = "normal"
        except:
            pass
    return result


# -------------------- 3. 辅助检查规则 --------------------
def nodule_risk(size_mm, grade):
    try:
        s = float(size_mm) if size_mm else 0
        g = str(grade) if grade else ""
        high_grade = False
        if g:
            grade_num = re.search(r'(\d+)', g)
            if grade_num and int(grade_num.group(1)) >= 4:
                high_grade = True
        if s >= 20 or high_grade:
            return "high"
        if s > 0:
            return "low"
        return "unknown"
    except:
        return "unknown"


def process_image(data):
    result = data.copy()

    if result.get("thyroid_nodule_present"):
        size = result.get("thyroid_nodule_size_mm")
        grade = result.get("thyroid_tirads_grade")
        result["thyroid_risk"] = nodule_risk(size, grade)

        grade_num = None
        if grade:
            g_match = re.search(r'(\d+)', str(grade))
            if g_match:
                grade_num = int(g_match.group(1))

        if grade_num and grade_num >= 4:
            result["thyroid_positive"] = True
            result["thyroid_recommendation"] = "需穿刺活检"
        elif grade_num == 3 and size and size > 20:
            result["thyroid_positive"] = True
            result["thyroid_recommendation"] = "需密切随访"
        else:
            result["thyroid_positive"] = False
            result["thyroid_recommendation"] = "常规随访"
    else:
        result["thyroid_risk"] = "none"
        result["thyroid_positive"] = False

    if result.get("lung_nodule_present"):
        size = result.get("lung_nodule_size_mm")
        density = result.get("lung_nodule_density", "")

        result["lung_nodule_risk"] = "low"
        result["lung_nodule_positive"] = False

        if size:
            if size >= 8:
                result["lung_nodule_risk"] = "moderate"
                result["lung_nodule_positive"] = True
            if size >= 15:
                result["lung_nodule_risk"] = "high"
            if "磨玻璃" in density and size >= 8:
                result["lung_recommendation"] = "6个月后复查CT"
            elif size >= 15:
                result["lung_recommendation"] = "建议进一步检查（PET-CT或活检）"
    else:
        result["lung_nodule_risk"] = "none"
        result["lung_nodule_positive"] = False

    return result


# -------------------- 4. 慢病风险规则 --------------------
def process_risk(data, demographic, lab):
    result = data.copy()

    sbp = result.get("ambp_systolic")
    dbp = result.get("ambp_diastolic")
    imt = result.get("carotid_imt")
    uacr = result.get("uacr")

    hypertension_risk = {"level": "low", "has_hypertension": False, "kidney_damage_risk": False}

    if sbp and dbp:
        if sbp >= 130 or dbp >= 80:
            hypertension_risk["has_hypertension"] = True

    if hypertension_risk["has_hypertension"] and imt and imt > 1.0:
        hypertension_risk["level"] = "moderate"
        if uacr and uacr >= 30:
            hypertension_risk["kidney_damage_risk"] = True
            hypertension_risk["level"] = "high"

    result["hypertension_risk"] = hypertension_risk

    age = demographic.get("age") if demographic else None
    glucose_judge_val = lab.get("glucose_judge") if lab else None
    bmi = demographic.get("bmi") if demographic else None

    diabetes_risk = {"level": "low", "is_diabetes": False, "high_risk_population": False}

    if glucose_judge_val == "diabetes":
        diabetes_risk["is_diabetes"] = True
        diabetes_risk["level"] = "diabetes"
    elif glucose_judge_val == "impaired":
        diabetes_risk["level"] = "moderate"
        if age and age >= 45 and bmi and bmi >= 24:
            diabetes_risk["high_risk_population"] = True
            diabetes_risk["level"] = "high"

    result["diabetes_risk"] = diabetes_risk

    ldct = result.get("ldct_finding", "")
    age = demographic.get("age") if demographic else None
    pack_year = demographic.get("smoking_pack_year") if demographic else 0

    lung_cancer_risk = {"level": "low", "has_nodule": False, "high_risk": False, "follow_up_plan": None}

    if ldct and "结节" in ldct:
        lung_cancer_risk["has_nodule"] = True
        size_match = re.search(r'(\d+)mm', ldct)
        if size_match:
            size = int(size_match.group(1))
            if size >= 6:
                lung_cancer_risk["level"] = "moderate"
                if age and age >= 50 and pack_year >= 20:
                    lung_cancer_risk["high_risk"] = True
                    lung_cancer_risk["level"] = "high"
                    lung_cancer_risk["follow_up_plan"] = "低剂量CT随访（6个月）"
                elif size >= 8:
                    lung_cancer_risk["follow_up_plan"] = "6个月后复查CT"

    result["lung_cancer_risk"] = lung_cancer_risk

    return result


# -------------------- 5. 量表规则 --------------------
def mmse_correction(raw_score, education_years):
    try:
        score = float(raw_score) if raw_score else None
        if score is None:
            return None
        edu = education_years if education_years else 12
        corrected = score
        if edu <= 6:
            corrected = score + 1
        elif edu > 12:
            corrected = score - 1
        if edu <= 6:
            has_impairment = corrected <= 17
        elif edu <= 12:
            has_impairment = corrected <= 24
        else:
            has_impairment = corrected <= 24
        return {
            "raw_score": score,
            "corrected_score": round(corrected, 1),
            "education_years": edu,
            "has_cognitive_impairment": has_impairment,
            "severity": "重度" if corrected < 10 else "中度" if corrected < 18 else "轻度" if corrected < 24 else "正常"
        }
    except:
        return None


def tcm_mapping(constitution):
    mapping = {
        "平和质": "01", "气虚质": "02", "阳虚质": "03",
        "阴虚质": "04", "痰湿质": "05", "湿热质": "06",
        "血瘀质": "07", "气郁质": "08", "特禀质": "09"
    }
    return mapping.get(constitution, "00")


def process_scale(data):
    result = data.copy()
    mmse_result = mmse_correction(result.get("mmse_raw_score"), result.get("education_years"))
    if mmse_result:
        result["mmse_processed"] = mmse_result
    tcm = result.get("tcm_constitution")
    if tcm:
        result["tcm_code"] = tcm_mapping(tcm)
    return result


# -------------------- 6. 人口学与行为规则 --------------------
def gender_code(gender):
    s = str(gender).strip() if gender else ""
    if "男" in s:
        return 1
    if "女" in s:
        return 2
    return 0


def smoking_pack_year(cig_per_day, years):
    try:
        cig = float(cig_per_day) if cig_per_day else 0
        y = float(years) if years else 0
        if cig > 0 and y > 0:
            return round((cig / 20.0) * y, 1)
        return 0
    except:
        return 0


def drinking_ethanol_grams(amount_liang, years, alcohol_percent=0.4):
    try:
        liang = float(amount_liang) if amount_liang else 0
        return round(liang * 50 * alcohol_percent * 0.8, 1)
    except:
        return 0


def process_demographic(data):
    result = data.copy()
    result["gender_code"] = gender_code(result.get("gender"))
    result["smoking_pack_year"] = smoking_pack_year(result.get("smoking_cig_per_day"), result.get("smoking_years"))
    result["smoking_high_risk"] = result["smoking_pack_year"] >= 20
    alcohol = result.get("drinking_amount_liang")
    if alcohol:
        result["drinking_ethanol_grams_per_day"] = drinking_ethanol_grams(alcohol, result.get("drinking_years"))
    if result.get("height") and result.get("weight"):
        result["bmi"] = calc_bmi(result.get("height"), result.get("weight"))
    return result


# ==============================================
# 主流程
# ==============================================

def load_config():
    with open("config.toml", "rb") as f:
        return tomli.load(f)


def read_pdf(path):
    text = ""
    try:
        reader = PdfReader(path)
        for page in reader.pages:
            text += page.extract_text() or ""
    except Exception as e:
        print(f"PDF读取错误 {path}: {e}")
    return text


def ai_extract(config, text, prompt):
    """调用AI提取数据 - 增强版JSON解析"""
    try:
        client = OpenAI(api_key=config["llm"]["api_key"], base_url=config["llm"]["base_url"])
        res = client.chat.completions.create(
            model=config["llm"]["model"],
            messages=[{"role": "user", "content": f"{prompt}\n\n体检报告文本：\n{text[:8000]}"}],
            temperature=0.1
        )
        content = res.choices[0].message.content.strip()

        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        brace_count = 0
        start = -1
        for i, ch in enumerate(content):
            if ch == '{':
                if brace_count == 0:
                    start = i
                brace_count += 1
            elif ch == '}':
                brace_count -= 1
                if brace_count == 0 and start != -1:
                    json_str = content[start:i + 1]
                    try:
                        return json.loads(json_str)
                    except:
                        continue

        import re
        content_no_comments = re.sub(r'//.*?\n', '\n', content)
        content_no_comments = re.sub(r'/\*.*?\*/', '', content_no_comments, flags=re.DOTALL)

        try:
            return json.loads(content_no_comments)
        except:
            pass

        print(f"JSON解析失败，原始内容前500字符:\n{content[:500]}")
        return {}

    except Exception as e:
        print(f"AI提取错误: {e}")
        return {}


def main():
    config = load_config()
    # 修改输出文件为 .json
    out = config["paths"]["output_file"].replace(".jsonl", ".json")
    os.makedirs(os.path.dirname(out), exist_ok=True)

    # 存储所有结果
    all_results = []

    for fname in os.listdir(config["paths"]["input_folder"]):
        if not fname.lower().endswith(".pdf"):
            continue
        print(f"正在处理: {fname}")
        text = read_pdf(os.path.join(config["paths"]["input_folder"], fname))

        if not text:
            print(f"警告: {fname} 无法读取内容")
            continue

        cr = config["clean_rules"]

        vitals_data = ai_extract(config, text, cr["vitals"]["prompt"])
        vitals = process_vitals(vitals_data)

        lab_data = ai_extract(config, text, cr["lab"]["prompt"])
        lab = process_lab(lab_data)

        image_data = ai_extract(config, text, cr["image"]["prompt"])
        image = process_image(image_data)

        demo_data = ai_extract(config, text, cr["demographic"]["prompt"])
        if vitals.get("height"):
            demo_data["height"] = vitals["height"]
        if vitals.get("weight"):
            demo_data["weight"] = vitals["weight"]
        demographic = process_demographic(demo_data)

        risk_data = ai_extract(config, text, cr["risk"]["prompt"])
        risk = process_risk(risk_data, demographic, lab)

        scale_data = ai_extract(config, text, cr["scale"]["prompt"])
        scale = process_scale(scale_data)

        result = {
            "file": fname,
            "data": {
                "vitals": vitals,
                "lab": lab,
                "image": image,
                "risk": risk,
                "scale": scale,
                "demographic": demographic
            }
        }

        all_results.append(result)
        print(f"完成: {fname}")

    # 输出单个JSON文件（数组格式）
    with open(out, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    print(f"✅ 六大清洗规则执行完成，共处理 {len(all_results)} 个文件")
    print(f"输出文件: {out}")


if __name__ == "__main__":
    main()