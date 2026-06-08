from datetime import datetime, timedelta

from sqlalchemy import select

from app import models, services
from app.database import SessionLocal, init_db
from app.schemas import ArticleImportItem


def seed_accounts(db) -> None:
    if db.scalars(select(models.WechatAccount)).first():
        return
    academic = models.WechatAccount(
        name="募格学术",
        positioning="面向科研群体的学术资讯、科研生态、论文投稿、基金申报与研究生成长账号。",
        core_readers="研究生、博士、博士后、青年教师、科研人员",
        publish_frequency="工作日",
        review_level="严格审核",
    )
    recruit = models.WechatAccount(
        name="募格科聘",
        positioning="面向博士和科研人才的高校招聘、博士就业、博士后机会与人才政策账号。",
        core_readers="博士、博士后、青年教师、科研求职者、高校招聘方",
        publish_frequency="工作日",
        review_level="严格审核",
    )
    db.add_all([academic, recruit])
    db.flush()
    academic_columns = {
        "科研热点": "学术新闻、论文突破、科研动态",
        "论文投稿": "投稿经验、期刊选择、审稿、返修、拒稿",
        "基金项目": "国自然、社科基金、青年基金、项目申报",
        "学术规范": "撤稿、署名、数据造假、学术伦理",
        "读研读博": "导师关系、读博经验、毕业压力、科研训练",
        "工具方法": "AI 工具、文献管理、统计工具、写作工具",
    }
    recruit_columns = {
        "高校招聘": "高校教师、科研岗、实验岗、科研管理岗",
        "博士就业": "博士求职、简历、面试、职业选择",
        "博士后机会": "博士后招聘、待遇、出站发展",
        "青年人才": "青年人才项目、人才引进政策",
        "简历面试": "简历优化、面试经验、试讲准备",
        "招聘观察": "高校用人趋势、学科需求、人才流动",
    }
    for name, direction in academic_columns.items():
        db.add(models.ContentColumn(account_id=academic.id, name=name, direction=direction))
    for name, direction in recruit_columns.items():
        db.add(models.ContentColumn(account_id=recruit.id, name=name, direction=direction))
    db.add(
        models.AccountProfile(
            account_id=academic.id,
            forbidden_topics=["未经核实的学术指控", "夸大科研成果", "具体人物定性评价"],
            tone_keywords=["严谨", "理性", "实用", "适度共鸣"],
            title_preferences=["信息型", "问题型", "清单型", "观察型"],
        )
    )
    db.add(
        models.AccountProfile(
            account_id=recruit.id,
            forbidden_topics=["未经授权的招聘包装", "承诺录用", "夸大待遇"],
            tone_keywords=["实用", "机会导向", "职业规划", "谨慎核实"],
            title_preferences=["机会型", "清单型", "决策型", "提醒型"],
        )
    )
    for account in [academic, recruit]:
        db.add(
            models.StyleTemplate(
                account_id=account.id,
                name=f"{account.name} 默认风格",
                writing_rules={
                    "structure": "背景-分析-建议",
                    "must_have": ["来源提示", "风险提醒", "可执行建议"],
                },
                title_banned_rules=["恐吓式表达", "绝对化结论", "未证实指控", "承诺式录用"],
                layout_rules={"heading": "清晰分级", "highlight": "重点句加粗", "ending": "关注/讨论引导"},
            )
        )
    db.commit()


def seed_articles(db) -> None:
    if db.scalars(select(models.HistoricalArticle)).first():
        return
    items = [
        ArticleImportItem(
            account_name="募格学术",
            title="历史知识库示例：基金申请书论证结构复盘",
            body="基金申请书需要关注科学问题、研究基础和可行性论证。历史文章只用于知识库检索和风格参考，不再自动翻新为当日选题。",
            published_at=datetime.utcnow() - timedelta(days=120),
            column_name="基金项目",
            reads=18000,
            likes=420,
            shares=260,
        ),
        ArticleImportItem(
            account_name="募格科聘",
            title="博士后出站后如何选择高校岗位",
            body="博士后出站求职需要同时评估学科平台、聘期考核、薪资待遇、编制政策和科研启动经费，所有条件应以官方公告为准。",
            published_at=datetime.utcnow() - timedelta(days=90),
            column_name="博士后机会",
            reads=22000,
            likes=510,
            shares=330,
        ),
        ArticleImportItem(
            account_name="募格学术",
            title="历史知识库示例：科研诚信报道的事实核查方法",
            body="科研诚信报道涉及数据管理、作者责任和公开来源核验。历史文章只作为写作参考，不代表当前热点。",
            published_at=datetime.utcnow() - timedelta(days=45),
            column_name="学术规范",
            reads=26000,
            likes=630,
            shares=480,
        ),
    ]
    services.import_articles(db, items, "seed")


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        seed_accounts(db)
        seed_articles(db)
        services.run_monitors(db, [], "seed")
        services.generate_topics(db, None, 4, "seed")
    finally:
        db.close()


if __name__ == "__main__":
    main()
