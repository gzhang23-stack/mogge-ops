from __future__ import annotations

import csv
import hashlib
import io
import math
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import quote_plus, urlparse

import httpx
from bs4 import BeautifulSoup
from markdown import markdown
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app import models
from app import automation
from app.config import get_settings
from app.llm import LLMClient
from app.notifier import DingTalkNotifier
from app.schemas import ArticleImportItem
from app.schemas import MetricImportItem
from app.schemas import LinkInboxRequest, WechatArticleMonitorItem, WechatMonitorAccountItem
from app.wechat_api import WeChatApiError, sync_article_datacube


ACADEMIC_KEYWORDS = ["论文", "投稿", "基金", "撤稿", "导师", "学术", "科研", "博士", "博士后"]
RECRUIT_KEYWORDS = ["招聘", "岗位", "高校", "待遇", "编制", "求职", "人才", "简历", "面试"]
HIGH_RISK_KEYWORDS = ["举报", "撤稿", "造假", "学术不端", "指控", "争议", "实名", "投诉"]
MEDIUM_RISK_KEYWORDS = ["政策", "待遇", "薪资", "编制", "安家费", "具体高校", "截止时间"]
STRICT_CHINESE_MONITOR_KEYWORDS = [
    "撤稿",
    "学术不端",
    "博士",
    "硕士",
    "导师",
    "博导",
    "硕导",
    "大学",
    "高校",
    "论文",
    "科研",
    "研究生",
    "杰青",
    "长江学者",
    "院士",
]
STRICT_CHINESE_NEWS_SOURCES = [
    "科学网-所有新闻",
    "九派新闻",
    "现代快报",
    "大河报",
    "华商报",
    "澎湃新闻",
    "扬子晚报",
    "界面新闻",
    "极目新闻",
    "红星新闻",
    "中国青年报",
    "上游新闻",
]
STRICT_ENGLISH_SOURCES = {"Nature News", "Retraction Watch", "Science News"}
DOMESTIC_NEWS_WINDOW_HOURS = 24
ENGLISH_NEWS_WINDOW_HOURS = 72
SOCIAL_CLUE_CONTENT_TYPE = "social_clue"
SOCIAL_LINK_RE = re.compile(r"https?://[^\s<>'\"，,。；;）)\]】]+")
SOCIAL_MONITOR_KEYWORDS = sorted(
    set(
        STRICT_CHINESE_MONITOR_KEYWORDS
        + [
            "教授",
            "校长",
            "大学生",
            "考研",
            "保研",
            "毕业",
            "实验室",
            "期刊",
            "SCI",
            "博士后",
            "青椒",
            "职称",
            "基金",
            "投稿",
            "招聘",
            "编制",
            "高校人才",
            "科研评价",
        ]
    )
)

DEFAULT_MONITOR_SOURCES = [
    # 国内：科学网/中国科学报公开 RSS，适合中文学术新闻、论文、基金和人才高教。
    {
        "name": "科学网-所有新闻",
        "source_type": "domestic_rss",
        "url": "http://www.sciencenet.cn/xml/news-0.aspx?news=0",
        "credibility_level": "中国科学报社公开 RSS",
        "account_bias": "募格学术",
        "keywords": ["科学网", "科研", "学术新闻"],
        "notes": "科学网新闻全量 RSS。",
    },
    {
        "name": "科学网-首页要闻",
        "source_type": "domestic_rss",
        "url": "http://www.sciencenet.cn/xml/news-0.aspx?di=1",
        "credibility_level": "中国科学报社公开 RSS",
        "account_bias": "募格学术",
        "keywords": ["要闻", "科研", "政策"],
        "notes": "科学网首页要闻，适合每日热点扫描。",
    },
    {
        "name": "科学网-国际快讯",
        "source_type": "domestic_rss",
        "url": "http://www.sciencenet.cn/xml/news-0.aspx?di=7",
        "credibility_level": "中国科学报社公开 RSS",
        "account_bias": "募格学术",
        "keywords": ["国际", "科研", "顶刊"],
        "notes": "国际科研动态中文快讯。",
    },
    {
        "name": "科学网-HOT论文",
        "source_type": "domestic_rss",
        "url": "http://www.sciencenet.cn/xml/news-0.aspx?di=8",
        "credibility_level": "中国科学报社公开 RSS",
        "account_bias": "募格学术",
        "keywords": ["论文", "顶刊", "成果"],
        "notes": "适合顶刊论文解读和科研前沿选题。",
    },
    {
        "name": "科学网-人才高教",
        "source_type": "domestic_rss",
        "url": "http://www.sciencenet.cn/xml/news-0.aspx?di=9",
        "credibility_level": "中国科学报社公开 RSS",
        "account_bias": "募格科聘",
        "keywords": ["人才", "高校", "博士", "招聘"],
        "notes": "适合募格科聘的人才、高教、求职观察。",
    },
    {
        "name": "科学网-前沿交叉",
        "source_type": "domestic_rss",
        "url": "http://www.sciencenet.cn/xml/field.aspx?di=4",
        "credibility_level": "中国科学报社公开 RSS",
        "account_bias": "募格学术",
        "keywords": ["交叉学科", "科研前沿"],
        "notes": "前沿交叉领域动态。",
    },
    {
        "name": "科学网-政策管理",
        "source_type": "domestic_rss",
        "url": "http://www.sciencenet.cn/xml/field.aspx?di=5",
        "credibility_level": "中国科学报社公开 RSS",
        "account_bias": "募格学术",
        "keywords": ["政策", "科研管理", "基金"],
        "notes": "科研政策、管理和基金相关动态。",
    },
    {
        "name": "科学网-基础科学",
        "source_type": "domestic_rss",
        "url": "http://www.sciencenet.cn/xml/field.aspx?di=7",
        "credibility_level": "中国科学报社公开 RSS",
        "account_bias": "募格学术",
        "keywords": ["基础科学", "论文", "成果"],
        "notes": "基础科学成果监控。",
    },
    {
        "name": "科学网-信息科学",
        "source_type": "domestic_rss",
        "url": "http://www.sciencenet.cn/xml/field.aspx?di=9",
        "credibility_level": "中国科学报社公开 RSS",
        "account_bias": "募格学术",
        "keywords": ["信息科学", "AI", "计算机"],
        "notes": "信息科学和 AI 科研动态。",
    },
    {
        "name": "科学网-论文频道",
        "source_type": "domestic_rss",
        "url": "http://www.sciencenet.cn/xml/paper.aspx?di=0",
        "credibility_level": "中国科学报社公开 RSS",
        "account_bias": "募格学术",
        "keywords": ["论文", "小柯机器人", "期刊"],
        "notes": "论文频道全量 RSS。",
    },
    {
        "name": "科学网-招生招聘",
        "source_type": "domestic_rss",
        "url": "http://www.sciencenet.cn/xml/classinfo.aspx",
        "credibility_level": "中国科学报社公开 RSS",
        "account_bias": "募格科聘",
        "keywords": ["招聘", "招生", "博士后", "高校"],
        "notes": "科研相关招聘与招生信息，转稿时必须人工核实。",
    },
    {
        "name": "科学网博客-编辑推荐",
        "source_type": "domestic_rss",
        "url": "http://www.sciencenet.cn/xml/blog.aspx?di=20",
        "credibility_level": "科学网博客公开 RSS",
        "account_bias": "募格学术",
        "keywords": ["科研观察", "学术评论"],
        "notes": "适合观点类、观察类选题参考。",
    },
    {
        "name": "科学网博客-科研笔记",
        "source_type": "domestic_rss",
        "url": "http://www.sciencenet.cn/xml/blog.aspx?di=1",
        "credibility_level": "科学网博客公开 RSS",
        "account_bias": "募格学术",
        "keywords": ["科研笔记", "经验", "方法"],
        "notes": "适合方法、经验、研究生成长类选题。",
    },
    {
        "name": "中国科学院-科研进展",
        "source_type": "html_list",
        "url": "https://www.cas.cn/syky/",
        "credibility_level": "中国科学院官网公开页面",
        "account_bias": "募格学术",
        "keywords": ["中科院", "科研进展", "成果"],
        "notes": "官网列表页，无稳定 RSS 时按页面标题抓取。",
    },
    {
        "name": "国家自然科学基金委-首页动态",
        "source_type": "html_list",
        "url": "https://www.nsfc.gov.cn/",
        "credibility_level": "国家自然科学基金委员会官网",
        "account_bias": "募格学术",
        "keywords": ["基金", "项目指南", "通知"],
        "notes": "基金指南、通知和委内动态，需人工核实原文。",
    },
    {
        "name": "高校科技-权威高校科技资讯",
        "source_type": "html_list",
        "url": "https://gxkj.resource.edu.cn/",
        "credibility_level": "高校科技资讯公开页面",
        "account_bias": "募格科聘",
        "keywords": ["高校科技", "博士后基金", "高校", "成果转化"],
        "notes": "高校科技、博士后基金、高校政策类聚合页。",
    },
    # 国外：科研新闻、基金政策、预印本和学术规范。
    {
        "name": "Nature News",
        "source_type": "academic_rss",
        "url": "https://www.nature.com/nature.rss",
        "credibility_level": "期刊/媒体公开 RSS",
        "account_bias": "募格学术",
        "keywords": ["科研", "论文", "学术"],
        "notes": "Nature 公开 RSS，用于科研前沿观察。",
    },
    {
        "name": "ScienceDaily-All Science",
        "source_type": "academic_rss",
        "url": "https://www.sciencedaily.com/rss/all.xml",
        "credibility_level": "科学资讯公开 RSS",
        "account_bias": "募格学术",
        "keywords": ["science", "research", "paper"],
        "notes": "ScienceDaily 全量科学新闻 RSS，适合快速发现海外研究热点。",
    },
    {
        "name": "ScienceDaily Education",
        "source_type": "academic_rss",
        "url": "https://www.sciencedaily.com/rss/education_learning.xml",
        "credibility_level": "科学资讯公开 RSS",
        "account_bias": "募格学术",
        "keywords": ["科研", "教育", "博士"],
        "notes": "ScienceDaily 教育与学习 RSS，适合方法和趋势类选题。",
    },
    {
        "name": "EurekAlert-All Releases",
        "source_type": "academic_rss",
        "url": "https://www.eurekalert.org/rss.xml",
        "credibility_level": "AAAS EurekAlert 公开 RSS",
        "account_bias": "募格学术",
        "keywords": ["press release", "research", "university"],
        "notes": "全球高校、期刊和科研机构新闻稿聚合，需注意新闻稿口径。",
    },
    {
        "name": "Phys.org-Latest",
        "source_type": "academic_rss",
        "url": "https://phys.org/rss-feed/",
        "credibility_level": "Phys.org 公开 RSS",
        "account_bias": "募格学术",
        "keywords": ["science", "research", "technology"],
        "notes": "综合科学技术新闻，使用时保留来源署名。",
    },
    {
        "name": "Phys.org-Education",
        "source_type": "academic_rss",
        "url": "https://phys.org/rss-feed/science-news/education/",
        "credibility_level": "Phys.org 公开 RSS",
        "account_bias": "募格学术",
        "keywords": ["education", "higher education", "STEM"],
        "notes": "教育、高教和 STEM 教育研究动态。",
    },
    {
        "name": "Phys.org-Physics",
        "source_type": "academic_rss",
        "url": "https://phys.org/rss-feed/physics-news/",
        "credibility_level": "Phys.org 公开 RSS",
        "account_bias": "募格学术",
        "keywords": ["physics", "quantum", "materials"],
        "notes": "物理、量子和材料相关动态。",
    },
    {
        "name": "Phys.org-Biology",
        "source_type": "academic_rss",
        "url": "https://phys.org/rss-feed/biology-news/",
        "credibility_level": "Phys.org 公开 RSS",
        "account_bias": "募格学术",
        "keywords": ["biology", "life sciences"],
        "notes": "生命科学研究动态。",
    },
    {
        "name": "Retraction Watch",
        "source_type": "academic_rss",
        "url": "https://retractionwatch.com/feed/",
        "credibility_level": "撤稿观察公开 RSS",
        "account_bias": "募格学术",
        "keywords": ["撤稿", "学术规范", "科研诚信"],
        "notes": "默认高风险，转选题后必须严格审核。",
    },
    {
        "name": "NIH News Releases",
        "source_type": "academic_rss",
        "url": "https://www.nih.gov/news-releases/feed.xml",
        "credibility_level": "NIH 官方 RSS",
        "account_bias": "募格学术",
        "keywords": ["NIH", "medical research", "funding"],
        "notes": "美国 NIH 医学科研新闻和资助研究动态。",
    },
    {
        "name": "NSF News",
        "source_type": "academic_rss",
        "url": "https://www.nsf.gov/rss/rss_www_news.xml",
        "credibility_level": "NSF 官方 RSS",
        "account_bias": "募格学术",
        "keywords": ["NSF", "research", "funding"],
        "notes": "美国 NSF 科研新闻和创新动态。",
    },
    {
        "name": "NSF Funding Opportunities",
        "source_type": "academic_rss",
        "url": "https://www.nsf.gov/rss/rss_www_funding_pgm_annc_inf.xml",
        "credibility_level": "NSF 官方 RSS",
        "account_bias": "募格学术",
        "keywords": ["NSF", "funding", "grant"],
        "notes": "美国 NSF 资助机会，可用于国际基金政策观察。",
    },
    {
        "name": "medRxiv-All Articles",
        "source_type": "academic_rss",
        "url": "http://connect.medrxiv.org/medrxiv_xml.php?subject=all",
        "credibility_level": "medRxiv 公开 Atom/RSS",
        "account_bias": "募格学术",
        "keywords": ["preprint", "medical", "health sciences"],
        "notes": "医学预印本，所有内容必须标注未同行评议。",
    },
    {
        "name": "bioRxiv-All Articles",
        "source_type": "academic_rss",
        "url": "http://connect.biorxiv.org/biorxiv_xml.php?subject=all",
        "credibility_level": "bioRxiv 公开 Atom/RSS",
        "account_bias": "募格学术",
        "keywords": ["preprint", "biology", "life sciences"],
        "notes": "生命科学预印本，所有内容必须标注未同行评议。",
    },
    {
        "name": "arXiv-CS-AI",
        "source_type": "academic_rss",
        "url": "https://rss.arxiv.org/rss/cs.AI",
        "credibility_level": "arXiv 公开 RSS",
        "account_bias": "募格学术",
        "keywords": ["AI", "arXiv", "preprint"],
        "notes": "AI 预印本，需避免将预印本当作已审定成果。",
    },
    {
        "name": "arXiv-CS-CL",
        "source_type": "academic_rss",
        "url": "https://rss.arxiv.org/rss/cs.CL",
        "credibility_level": "arXiv 公开 RSS",
        "account_bias": "募格学术",
        "keywords": ["NLP", "LLM", "arXiv"],
        "notes": "自然语言处理和大模型预印本。",
    },
    {
        "name": "arXiv-Statistics-ML",
        "source_type": "academic_rss",
        "url": "https://rss.arxiv.org/rss/stat.ML",
        "credibility_level": "arXiv 公开 RSS",
        "account_bias": "募格学术",
        "keywords": ["machine learning", "statistics", "preprint"],
        "notes": "机器学习和统计预印本。",
    },
    {
        "name": "arXiv-CS-LG",
        "source_type": "academic_rss",
        "url": "https://rss.arxiv.org/rss/cs.LG",
        "credibility_level": "arXiv 公开 RSS",
        "account_bias": "募格学术",
        "keywords": ["machine learning", "AI", "preprint"],
        "notes": "机器学习预印本，适合 AI 工具和科研方法选题。",
    },
    {
        "name": "arXiv-Physics",
        "source_type": "academic_rss",
        "url": "https://rss.arxiv.org/rss/physics",
        "credibility_level": "arXiv 公开 RSS",
        "account_bias": "募格学术",
        "keywords": ["physics", "preprint", "research"],
        "notes": "物理学预印本，需标注未同行评议。",
    },
    {
        "name": "arXiv-Quantitative Biology",
        "source_type": "academic_rss",
        "url": "https://rss.arxiv.org/rss/q-bio",
        "credibility_level": "arXiv 公开 RSS",
        "account_bias": "募格学术",
        "keywords": ["biology", "preprint", "research"],
        "notes": "定量生物学预印本，需标注未同行评议。",
    },
    {
        "name": "PNAS-Current Issue",
        "source_type": "academic_rss",
        "url": "https://www.pnas.org/action/showFeed?type=etoc&feed=rss&jc=pnas",
        "credibility_level": "PNAS 公开 RSS",
        "account_bias": "募格学术",
        "keywords": ["PNAS", "paper", "research"],
        "notes": "PNAS 最新期刊目录，适合论文解读。",
    },
    {
        "name": "Science-Current Issue",
        "source_type": "academic_rss",
        "url": "https://www.science.org/action/showFeed?type=etoc&feed=rss&jc=science",
        "credibility_level": "Science 公开 RSS",
        "account_bias": "募格学术",
        "keywords": ["Science", "paper", "research"],
        "notes": "Science 最新期刊目录，适合顶刊前沿监控。",
    },
    {
        "name": "Science Advances-Current Issue",
        "source_type": "academic_rss",
        "url": "https://www.science.org/action/showFeed?type=etoc&feed=rss&jc=sciadv",
        "credibility_level": "Science Advances 公开 RSS",
        "account_bias": "募格学术",
        "keywords": ["Science Advances", "paper", "research"],
        "notes": "Science Advances 最新论文目录。",
    },
    {
        "name": "Cell-Current Issue",
        "source_type": "academic_rss",
        "url": "https://www.cell.com/cell/current.rss",
        "credibility_level": "Cell Press 公开 RSS",
        "account_bias": "募格学术",
        "keywords": ["Cell", "life sciences", "paper"],
        "notes": "Cell 最新期刊目录，适合生命科学前沿监控。",
    },
    {
        "name": "Cell Reports-Current Issue",
        "source_type": "academic_rss",
        "url": "https://www.cell.com/cell-reports/current.rss",
        "credibility_level": "Cell Press 公开 RSS",
        "account_bias": "募格学术",
        "keywords": ["Cell Reports", "life sciences", "paper"],
        "notes": "Cell Reports 最新论文目录。",
    },
    {
        "name": "Trends in Cognitive Sciences",
        "source_type": "academic_rss",
        "url": "https://www.cell.com/trends/cognitive-sciences/current.rss",
        "credibility_level": "Cell Press 公开 RSS",
        "account_bias": "募格学术",
        "keywords": ["cognitive science", "review", "paper"],
        "notes": "认知科学综述和趋势文章，适合深度选题。",
    },
    {
        "name": "The Scientist",
        "source_type": "academic_rss",
        "url": "https://www.the-scientist.com/rss/feed",
        "credibility_level": "科研媒体公开 RSS",
        "account_bias": "募格学术",
        "keywords": ["biology", "research", "lab"],
        "notes": "生命科学新闻和实验室生态观察。",
    },
    {
        "name": "MIT News-Research",
        "source_type": "academic_rss",
        "url": "https://news.mit.edu/rss/topic/research",
        "credibility_level": "高校官方 RSS",
        "account_bias": "募格学术",
        "keywords": ["MIT", "research", "university"],
        "notes": "MIT 官方科研新闻。",
    },
    {
        "name": "Stanford News-Science",
        "source_type": "academic_rss",
        "url": "https://news.stanford.edu/rss/science-technology/feed/",
        "credibility_level": "高校官方 RSS",
        "account_bias": "募格学术",
        "keywords": ["Stanford", "science", "technology"],
        "notes": "斯坦福科学与技术新闻。",
    },
    {
        "name": "Harvard Gazette-Science",
        "source_type": "academic_rss",
        "url": "https://news.harvard.edu/gazette/section/science-technology/feed/",
        "credibility_level": "高校官方 RSS",
        "account_bias": "募格学术",
        "keywords": ["Harvard", "science", "technology"],
        "notes": "哈佛科学与技术新闻。",
    },
    {
        "name": "UC Berkeley News-Research",
        "source_type": "academic_rss",
        "url": "https://news.berkeley.edu/feed/",
        "credibility_level": "高校官方 RSS",
        "account_bias": "募格学术",
        "keywords": ["Berkeley", "research", "university"],
        "notes": "伯克利新闻，需从标题筛选科研、高教和人才相关内容。",
    },
    {
        "name": "Research Professional News",
        "source_type": "academic_rss",
        "url": "https://www.researchprofessionalnews.com/rr-news/rss/",
        "credibility_level": "科研政策媒体公开 RSS",
        "account_bias": "募格学术",
        "keywords": ["research policy", "funding", "higher education"],
        "notes": "科研政策、经费和高教生态新闻。",
    },
    {
        "name": "LSE Impact Blog",
        "source_type": "academic_rss",
        "url": "https://blogs.lse.ac.uk/impactofsocialsciences/feed/",
        "credibility_level": "高校学术传播博客 RSS",
        "account_bias": "募格学术",
        "keywords": ["open science", "peer review", "research impact"],
        "notes": "开放科学、同行评议、科研评价和学术传播。",
    },
    {
        "name": "Inside Higher Ed-News",
        "source_type": "academic_rss",
        "url": "https://www.insidehighered.com/rss/news",
        "credibility_level": "高教媒体公开 RSS",
        "account_bias": "募格科聘",
        "keywords": ["higher education", "faculty", "jobs", "PhD"],
        "notes": "美国高教、人事、教师和博士职业生态新闻。",
    },
    {
        "name": "Times Higher Education",
        "source_type": "academic_rss",
        "url": "https://www.timeshighereducation.com/rss.xml",
        "credibility_level": "高教媒体公开 RSS",
        "account_bias": "募格科聘",
        "keywords": ["higher education", "university", "ranking", "jobs"],
        "notes": "全球高教新闻、大学政策、排名和人才趋势。",
    },
    {
        "name": "Nature Careers",
        "source_type": "html_list",
        "url": "https://www.nature.com/naturecareers",
        "credibility_level": "Nature Careers 公开页面",
        "account_bias": "募格科聘",
        "keywords": ["career", "PhD", "postdoc", "jobs"],
        "notes": "科研职业、博士后和青年科研人员发展话题。",
    },
    {
        "name": "中国科学院-院地合作",
        "source_type": "html_list",
        "url": "https://www.cas.cn/yzhz/",
        "credibility_level": "中国科学院官网公开页面",
        "account_bias": "募格学术",
        "keywords": ["中科院", "成果转化", "合作"],
        "notes": "中科院合作与成果转化动态。",
    },
    {
        "name": "中国科学院-人才招聘",
        "source_type": "html_list",
        "url": "https://www.cas.cn/rc/gz/",
        "credibility_level": "中国科学院官网公开页面",
        "account_bias": "募格科聘",
        "keywords": ["中科院", "招聘", "博士后", "岗位"],
        "notes": "中科院系统招聘和岗位信息，转发前必须核实原始公告。",
    },
    {
        "name": "科技部-要闻动态",
        "source_type": "html_list",
        "url": "https://www.most.gov.cn/kjbgz/",
        "credibility_level": "科技部官网公开页面",
        "account_bias": "募格学术",
        "keywords": ["科技部", "政策", "科研"],
        "notes": "科技政策、科研管理和国家科技动态。",
    },
    {
        "name": "教育部-新闻发布",
        "source_type": "html_list",
        "url": "http://www.moe.gov.cn/jyb_xwfb/",
        "credibility_level": "教育部官网公开页面",
        "account_bias": "募格科聘",
        "keywords": ["教育部", "高校", "人才", "博士"],
        "notes": "高教政策、教育发布和人才相关动态。",
    },
    {
        "name": "教育部-高等教育司",
        "source_type": "html_list",
        "url": "http://www.moe.gov.cn/s78/A08/",
        "credibility_level": "教育部官网公开页面",
        "account_bias": "募格科聘",
        "keywords": ["高等教育", "高校", "教师", "人才"],
        "notes": "高等教育政策和高校治理动态。",
    },
    {
        "name": "中国博士后-通知公告",
        "source_type": "html_list",
        "url": "https://www.chinapostdoctor.org.cn/",
        "credibility_level": "中国博士后官网公开页面",
        "account_bias": "募格科聘",
        "keywords": ["博士后", "基金", "招聘", "出站"],
        "notes": "博士后政策、基金和通知公告，需人工核实原文。",
    },
    {
        "name": "中国教育在线-高教",
        "source_type": "html_list",
        "url": "https://gaojiao.eol.cn/",
        "credibility_level": "高教媒体公开页面",
        "account_bias": "募格科聘",
        "keywords": ["高校", "高教", "人才", "博士"],
        "notes": "中文高教新闻和高校动态。",
    },
    {
        "name": "青塔-高教资讯",
        "source_type": "html_list",
        "url": "https://www.cingta.com/",
        "credibility_level": "高教媒体公开页面",
        "account_bias": "募格科聘",
        "keywords": ["高校", "人才", "学科", "招聘"],
        "notes": "高教资讯、人才和学科动态，需核实原文和版权。",
    },
    {
        "name": "软科-高教资讯",
        "source_type": "html_list",
        "url": "https://www.shanghairanking.cn/news/",
        "credibility_level": "高教媒体公开页面",
        "account_bias": "募格科聘",
        "keywords": ["大学", "排名", "学科", "高校"],
        "notes": "高校、学科和排名相关动态。",
    },
    {
        "name": "学术头条",
        "source_type": "html_list",
        "url": "https://www.scholarnet.cn/",
        "credibility_level": "学术媒体公开页面",
        "account_bias": "募格学术",
        "keywords": ["科研", "论文", "基金", "学术"],
        "notes": "中文学术资讯源，需核实原文和版权。",
    },
    {
        "name": "微信公众号-学术志",
        "source_type": "wechat_account",
        "url": "",
        "credibility_level": "微信公众号公开文章",
        "account_bias": "募格学术",
        "keywords": ["学术", "论文", "科研", "博士"],
        "notes": "优先通过 RSSHub/WeWe-RSS 配置微信号或人工粘贴文章链接；不绕过微信平台限制。",
    },
    {
        "name": "微信公众号-募格学术",
        "source_type": "wechat_account",
        "url": "",
        "credibility_level": "自有公众号",
        "account_bias": "募格学术",
        "keywords": ["募格学术", "科研", "论文", "基金"],
        "notes": "自有账号历史和新稿监控，可后续接入授权数据或文章链接。",
    },
    {
        "name": "微信公众号-募格科聘",
        "source_type": "wechat_account",
        "url": "",
        "credibility_level": "自有公众号",
        "account_bias": "募格科聘",
        "keywords": ["募格科聘", "招聘", "博士后", "高校人才"],
        "notes": "自有账号招聘和人才内容监控，可后续接入授权数据或文章链接。",
    },
    {
        "name": "微信公众号-科研圈",
        "source_type": "wechat_account",
        "url": "",
        "credibility_level": "微信公众号公开文章",
        "account_bias": "募格学术",
        "keywords": ["科研", "科学", "论文", "学术"],
        "notes": "优先通过 RSSHub/WeWe-RSS 配置微信号或人工粘贴文章链接。",
    },
    {
        "name": "微信公众号-知识分子",
        "source_type": "wechat_account",
        "url": "",
        "credibility_level": "微信公众号公开文章",
        "account_bias": "募格学术",
        "keywords": ["科学", "科研", "科学家", "学术"],
        "notes": "优先通过 RSSHub/WeWe-RSS 配置微信号或人工粘贴文章链接。",
    },
    {
        "name": "微信公众号-生物世界",
        "source_type": "wechat_account",
        "url": "",
        "credibility_level": "微信公众号公开文章",
        "account_bias": "募格学术",
        "keywords": ["生物", "医学", "论文", "科研"],
        "notes": "优先通过 RSSHub/WeWe-RSS 配置微信号或人工粘贴文章链接。",
    },
    {
        "name": "微信公众号-高校人才网",
        "source_type": "wechat_account",
        "url": "",
        "credibility_level": "微信公众号公开文章",
        "account_bias": "募格科聘",
        "keywords": ["高校招聘", "博士后", "人才", "岗位"],
        "notes": "招聘信息必须回到原始公告核实，不直接承诺待遇和录用。",
    },
    {
        "name": "微信公众号-青塔人才",
        "source_type": "wechat_account",
        "url": "",
        "credibility_level": "微信公众号公开文章",
        "account_bias": "募格科聘",
        "keywords": ["高校人才", "招聘", "博士", "青年人才"],
        "notes": "招聘和人才政策类内容，需核实官方公告。",
    },
]


def audit(db: Session, actor: str, action: str, entity_type: str, entity_id: str = "", payload: dict | None = None) -> None:
    db.add(models.AuditLog(actor=actor, action=action, entity_type=entity_type, entity_id=entity_id, payload=payload or {}))


def summarize(text: str, limit: int = 120) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    return clean[:limit] + ("..." if len(clean) > limit else "")


def extract_tags(text: str, title: str = "") -> list[str]:
    joined = f"{title} {text}"
    tags = []
    for keyword in ACADEMIC_KEYWORDS + RECRUIT_KEYWORDS:
        if keyword in joined:
            tags.append(keyword)
    return sorted(set(tags or ["综合"]))


def infer_account(title: str, body: str) -> str:
    joined = f"{title} {body}"
    recruit_score = sum(1 for k in RECRUIT_KEYWORDS if k in joined)
    academic_score = sum(1 for k in ACADEMIC_KEYWORDS if k in joined)
    return "募格科聘" if recruit_score > academic_score else "募格学术"


def infer_column(account: str, text: str) -> str:
    if account == "募格科聘":
        if "博士后" in text:
            return "博士后机会"
        if "简历" in text or "面试" in text:
            return "简历面试"
        if "政策" in text or "人才" in text:
            return "青年人才"
        return "高校招聘"
    if "基金" in text:
        return "基金项目"
    if "投稿" in text or "论文" in text:
        return "论文投稿"
    if "撤稿" in text or "学术不端" in text:
        return "学术规范"
    return "科研热点"


def infer_risk(text: str) -> models.RiskLevel:
    if any(keyword in text for keyword in HIGH_RISK_KEYWORDS):
        return models.RiskLevel.high
    if any(keyword in text for keyword in MEDIUM_RISK_KEYWORDS):
        return models.RiskLevel.medium
    return models.RiskLevel.low


def _news_search_url(source_name: str) -> str:
    keywords = " OR ".join(STRICT_CHINESE_MONITOR_KEYWORDS)
    query = f'"{source_name}" ({keywords})'
    return f"https://www.bing.com/news/search?q={quote_plus(query)}&format=rss&setlang=zh-CN&mkt=zh-CN"


STRICT_DEFAULT_MONITOR_SOURCES = [
    {
        "name": "科学网-所有新闻",
        "source_type": "domestic_rss",
        "url": "http://www.sciencenet.cn/xml/news-0.aspx?news=0",
        "credibility_level": "中国科学报社公开 RSS",
        "account_bias": "募格学术",
        "keywords": STRICT_CHINESE_MONITOR_KEYWORDS,
        "notes": "科学网只保留所有新闻；入库必须命中关键词且发布时间在 24 小时内。",
    },
    *[
        {
            "name": source_name,
            "source_type": "news_search",
            "url": _news_search_url(source_name),
            "credibility_level": "公开新闻搜索/RSS",
            "account_bias": "募格学术",
            "keywords": STRICT_CHINESE_MONITOR_KEYWORDS,
            "notes": "中文新闻重点监控源；仅保存 24 小时内且命中关键词的原始新闻线索。",
        }
        for source_name in STRICT_CHINESE_NEWS_SOURCES
        if source_name != "科学网-所有新闻"
    ],
    {
        "name": "Nature News",
        "source_type": "academic_rss",
        "url": "https://www.nature.com/nature.rss",
        "credibility_level": "Nature 官方 RSS",
        "account_bias": "募格学术",
        "keywords": ["research", "science", "university", "paper", "retraction"],
        "notes": "英文前沿仅保留 Nature News；仅保存 72 小时内新闻并简要翻译。",
    },
    {
        "name": "Retraction Watch",
        "source_type": "academic_rss",
        "url": "https://retractionwatch.com/feed/",
        "credibility_level": "Retraction Watch 官方 RSS",
        "account_bias": "募格学术",
        "keywords": ["retraction", "misconduct", "paper", "research integrity"],
        "notes": "撤稿与科研诚信来源；仅保存 72 小时内新闻并简要翻译。",
    },
    {
        "name": "Science News",
        "source_type": "academic_rss",
        "url": "https://www.science.org/rss/news_current.xml",
        "credibility_level": "Science 官方 RSS",
        "account_bias": "募格学术",
        "keywords": ["science", "research", "university", "paper"],
        "notes": "英文前沿仅保留 Science News；仅保存 72 小时内新闻并简要翻译。",
    },
]


def ensure_monitor_schema(db: Session) -> None:
    try:
        db.execute(text("SELECT raw_payload FROM academic_monitor_items LIMIT 1"))
    except Exception:
        db.rollback()
        try:
            db.execute(text("ALTER TABLE academic_monitor_items ADD COLUMN raw_payload JSON DEFAULT '{}'"))
            db.commit()
        except Exception:
            db.rollback()


def ensure_default_monitor_sources(db: Session) -> None:
    from app.database import init_db

    init_db()
    ensure_monitor_schema(db)
    existing = {source.name: source for source in db.scalars(select(models.MonitorSource)).all()}
    allowed_names = {source["name"] for source in STRICT_DEFAULT_MONITOR_SOURCES}
    changed = False
    for name, current in existing.items():
        if current.source_type != "wechat_account" and name not in allowed_names:
            current.enabled = False
            current.notes = f"{current.notes}\n已停用：当前监控策略只保留指定中文新闻源、科学网所有新闻和三个英文前沿源。".strip()
            changed = True
    for source in STRICT_DEFAULT_MONITOR_SOURCES:
        current = existing.get(source["name"])
        if current:
            for key, value in source.items():
                if getattr(current, key) != value:
                    setattr(current, key, value)
                    changed = True
        else:
            db.add(models.MonitorSource(**source))
            changed = True
    if changed:
        db.commit()


def _existing_hot_event(db: Session, title: str, source_url: str = "") -> bool:
    canonical = canonical_monitor_key(title, source_url)
    for row in db.scalars(select(models.ExternalHotEvent).limit(500)).all():
        if canonical_monitor_key(row.event_title, row.source_url) == canonical:
            return True
    stmt = select(models.ExternalHotEvent.id).where(models.ExternalHotEvent.event_title == title)
    if source_url:
        stmt = stmt.where(models.ExternalHotEvent.source_url == source_url)
    return db.scalars(stmt).first() is not None


def _existing_academic_item(db: Session, title: str, source_url: str = "") -> bool:
    canonical = canonical_monitor_key(title, source_url)
    for row in db.scalars(select(models.AcademicMonitorItem).limit(500)).all():
        if canonical_monitor_key(row.original_title, row.source_url) == canonical:
            return True
    stmt = select(models.AcademicMonitorItem.id).where(models.AcademicMonitorItem.original_title == title)
    if source_url:
        stmt = stmt.where(models.AcademicMonitorItem.source_url == source_url)
    return db.scalars(stmt).first() is not None


def _rss_text(element: ET.Element, tag: str) -> str:
    node = element.find(tag)
    if node is None:
        node = element.find(f"{{*}}{tag}")
    return (node.text or "").strip() if node is not None else ""


def _rss_attr(element: ET.Element, tag: str, attr: str) -> str:
    node = element.find(tag)
    if node is None:
        node = element.find(f"{{*}}{tag}")
    return str(node.attrib.get(attr, "")).strip() if node is not None else ""


def parse_source_datetime(value: str) -> datetime | None:
    if not value:
        return None
    raw = value.strip()
    try:
        parsed = parsedate_to_datetime(raw)
    except Exception:
        parsed = None
    if parsed is None:
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            parsed = None
    if parsed is None:
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(raw, fmt)
                break
            except ValueError:
                continue
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def within_hours(published_at: datetime | None, hours: int) -> bool:
    if published_at is None:
        return False
    now = datetime.utcnow()
    return timedelta(0) <= now - published_at <= timedelta(hours=hours)


def keyword_hits(text: str, keywords: list[str]) -> list[str]:
    haystack = text.lower()
    hits = []
    for keyword in keywords:
        if keyword and keyword.lower() in haystack:
            hits.append(keyword)
    return hits


def canonical_monitor_key(title: str, source_url: str = "") -> str:
    normalized_title = re.sub(r"\s+", "", title).lower()
    normalized_url = re.sub(r"[?#].*$", "", source_url.strip().lower())
    return normalized_url or normalized_title


def clean_source_summary(summary: str) -> str:
    if not summary:
        return ""
    if "<" in summary and ">" in summary:
        return BeautifulSoup(summary, "html.parser").get_text(" ")
    return summary


def fetch_rss_items(source: models.MonitorSource, limit: int = 8) -> list[dict[str, str]]:
    if not source.url:
        return []
    try:
        with httpx.Client(timeout=12, follow_redirects=True) as client:
            response = client.get(source.url, headers={"User-Agent": "MoggeOpsMonitor/0.1"})
            response.raise_for_status()
        root = ET.fromstring(response.content)
    except Exception:
        return []
    items = root.findall(".//item")
    if not items:
        items = root.findall(".//{http://www.w3.org/2005/Atom}entry")
    parsed = []
    for item in items[:limit]:
        title = _rss_text(item, "title")
        link = _rss_text(item, "link")
        if not link:
            link_node = item.find("{http://www.w3.org/2005/Atom}link")
            link = link_node.attrib.get("href", "") if link_node is not None else ""
        summary = _rss_text(item, "description") or _rss_text(item, "summary")
        published = _rss_text(item, "pubDate") or _rss_text(item, "updated") or _rss_text(item, "published")
        source_name = _rss_text(item, "source") or _rss_attr(item, "source", "url")
        if title:
            parsed.append(
                {
                    "title": title,
                    "link": link,
                    "summary": clean_source_summary(summary),
                    "published": published,
                    "source_name": source_name,
                }
            )
    return parsed


def fetch_html_list_items(source: models.MonitorSource, limit: int = 8) -> list[dict[str, str]]:
    if not source.url:
        return []
    try:
        with httpx.Client(timeout=12, follow_redirects=True) as client:
            response = client.get(source.url, headers={"User-Agent": "MoggeOpsMonitor/0.1"})
            response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
    except Exception:
        return []
    items = []
    seen = set()
    for link in soup.find_all("a", href=True):
        title = re.sub(r"\s+", " ", link.get_text(" ")).strip()
        if len(title) < 8 or title in seen:
            continue
        if not any(keyword.lower() in title.lower() for keyword in source.keywords + ACADEMIC_KEYWORDS + RECRUIT_KEYWORDS):
            if len(items) > 0:
                continue
        href = str(link["href"])
        if href.startswith("/"):
            base = re.match(r"^https?://[^/]+", source.url)
            href = f"{base.group(0)}{href}" if base else href
        elif not href.startswith("http"):
            href = source.url.rstrip("/") + "/" + href
        seen.add(title)
        items.append({"title": title, "link": href, "summary": source.notes, "published": ""})
        if len(items) >= limit:
            break
    return items


def fetch_wechat_account_items(db: Session, source: models.MonitorSource, limit: int = 8) -> list[dict[str, str]]:
    auto_settings = automation.get_raw_settings(db)
    rsshub_base = str(auto_settings.get("rsshub_base_url") or "").strip().rstrip("/")
    if source.url.startswith("http"):
        rss_url = source.url
    elif rsshub_base and source.url:
        rss_url = f"{rsshub_base}/wechat/uread/{source.url}"
    else:
        return []
    proxy_source = models.MonitorSource(
        name=source.name,
        source_type="academic_rss",
        url=rss_url,
        enabled=True,
        credibility_level=source.credibility_level,
        account_bias=source.account_bias,
        keywords=source.keywords,
        notes=source.notes,
    )
    return fetch_rss_items(proxy_source, limit=limit)


def normalize_social_url(url: str) -> str:
    value = url.strip().strip(" \t\r\n，,。；;）)]】>\"'")
    if value.startswith("http://") or value.startswith("https://"):
        return value
    return ""


def extract_social_links(text: str, links: list[str] | None = None) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw_url in links or []:
        url = normalize_social_url(raw_url)
        if url and url not in seen:
            rows.append({"url": url, "line_title": ""})
            seen.add(url)
    for line in text.splitlines():
        urls = [normalize_social_url(match.group(0)) for match in SOCIAL_LINK_RE.finditer(line)]
        urls = [url for url in urls if url]
        if not urls:
            continue
        line_title = line
        for url in urls:
            line_title = line_title.replace(url, " ")
        line_title = re.sub(r"\s+", " ", line_title).strip(" ：:，,。-")
        for url in urls:
            if url in seen:
                continue
            rows.append({"url": url, "line_title": line_title})
            seen.add(url)
    return rows


def detect_social_platform(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if "mp.weixin.qq.com" in host:
        return "微信公众号"
    if "douyin.com" in host:
        return "抖音"
    if "xiaohongshu.com" in host or "xhslink.com" in host:
        return "小红书"
    if "channels.weixin.qq.com" in host:
        return "视频号"
    if "weibo.com" in host:
        return "微博"
    if "bilibili.com" in host:
        return "B站"
    if "zhihu.com" in host:
        return "知乎"
    return "公开链接"


def _meta_content(soup: BeautifulSoup, *names: str) -> str:
    for name in names:
        node = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        if node and node.get("content"):
            return str(node.get("content")).strip()
    return ""


def fetch_public_link_metadata(url: str) -> dict[str, str]:
    try:
        with httpx.Client(timeout=6, follow_redirects=True) as client:
            response = client.get(url, headers={"User-Agent": "MoggeOpsMonitor/0.1"})
            response.raise_for_status()
    except Exception:
        return {"final_url": url}
    soup = BeautifulSoup(response.text, "html.parser")
    title = _meta_content(soup, "og:title", "twitter:title")
    if not title and soup.title and soup.title.string:
        title = soup.title.string.strip()
    description = _meta_content(soup, "og:description", "description", "twitter:description")
    published_at = _meta_content(soup, "article:published_time", "datePublished", "pubdate", "publishdate")
    site_name = _meta_content(soup, "og:site_name", "application-name")
    return {
        "title": re.sub(r"\s+", " ", title).strip(),
        "summary": re.sub(r"\s+", " ", description).strip(),
        "published_at": published_at,
        "source_name": site_name,
        "final_url": str(response.url),
    }


def exact_url_key(url: str) -> str:
    return normalize_social_url(url).rstrip("/")


def _existing_social_clue(db: Session, url: str) -> bool:
    key = exact_url_key(url)
    if not key:
        return False
    for row in db.scalars(select(models.ExternalHotEvent).order_by(models.ExternalHotEvent.id.desc()).limit(1000)).all():
        raw = row.raw_payload if isinstance(row.raw_payload, dict) else {}
        candidates = [row.source_url, str(raw.get("original_url") or ""), str(raw.get("final_url") or "")]
        if any(exact_url_key(candidate) == key for candidate in candidates if candidate):
            return True
    return False


def _social_confidence(hits: list[str], published_at: datetime | None, platform: str) -> tuple[str, float]:
    score = 0.35
    if platform != "公开链接":
        score += 0.12
    if hits:
        score += min(0.28, len(hits) * 0.07)
    if published_at:
        score += 0.2
    if platform in {"微信公众号", "抖音", "小红书", "视频号"} and not published_at:
        score -= 0.08
    score = max(0.1, min(0.95, score))
    if score >= 0.72:
        return "high", score
    if score >= 0.48:
        return "medium", score
    return "low", score


def _confidence_label(score: float) -> str:
    if score >= 0.72:
        return "high"
    if score >= 0.48:
        return "medium"
    return "low"


def social_feedback_adjustment(db: Session, platform: str, source_name: str, hits: list[str]) -> tuple[float, list[str]]:
    penalty = 0.0
    signals: list[str] = []
    hit_set = set(hits)
    for row in db.scalars(select(models.ExternalHotEvent).order_by(models.ExternalHotEvent.updated_at.desc()).limit(200)).all():
        raw = row.raw_payload if isinstance(row.raw_payload, dict) else {}
        if raw.get("content_type") != SOCIAL_CLUE_CONTENT_TYPE or not raw.get("feedback"):
            continue
        row_source = str(raw.get("source_name") or "")
        overlap = hit_set.intersection(set(row.extracted_keywords or []))
        if row.source_platform == platform:
            penalty += 0.04
            signals.append(f"同平台反馈：{platform}")
        if source_name and row_source == source_name:
            penalty += 0.06
            signals.append(f"同来源反馈：{source_name}")
        if overlap:
            penalty += 0.04
            signals.append(f"同关键词反馈：{'、'.join(sorted(overlap))}")
        if penalty >= 0.25:
            break
    return min(0.25, penalty), signals[:3]


def ingest_link_inbox(db: Session, payload: LinkInboxRequest, actor: str) -> dict[str, Any]:
    entries = extract_social_links(payload.text, payload.links)
    created = 0
    skipped = 0
    created_items: list[dict[str, Any]] = []
    for entry in entries:
        original_url = entry["url"]
        if _existing_social_clue(db, original_url):
            skipped += 1
            continue
        metadata = fetch_public_link_metadata(original_url) if payload.fetch_metadata else {"final_url": original_url}
        final_url = normalize_social_url(metadata.get("final_url") or original_url) or original_url
        if final_url != original_url and _existing_social_clue(db, final_url):
            skipped += 1
            continue
        platform = detect_social_platform(final_url or original_url)
        source_name = payload.source_name.strip() or metadata.get("source_name") or platform
        title = entry.get("line_title") or metadata.get("title") or f"{platform}线索：{urlparse(final_url or original_url).netloc}"
        title = summarize(title, 120)
        summary = metadata.get("summary") or "来自公开链接收件箱的社交平台线索，需要人工打开原文核实发布时间和事实。"
        parsed_published_at = payload.published_at or parse_source_datetime(str(metadata.get("published_at") or ""))
        text_for_keywords = f"{title} {summary} {platform} {source_name}"
        hits = keyword_hits(text_for_keywords, SOCIAL_MONITOR_KEYWORDS)
        confidence_label, confidence_score = _social_confidence(hits, parsed_published_at, platform)
        feedback_penalty, feedback_signals = social_feedback_adjustment(db, platform, source_name, hits)
        confidence_score = max(0.1, confidence_score - feedback_penalty)
        confidence_label = _confidence_label(confidence_score)
        heat = 45 + min(25, len(hits) * 5)
        if payload.mark_as_major:
            heat = max(heat, 90)
        elif platform in {"微信公众号", "抖音", "小红书", "视频号"}:
            heat += 5
        heat = max(20, heat - int(feedback_penalty * 80))
        event = models.ExternalHotEvent(
            event_title=title,
            heat_index=min(100, heat),
            source_platform=platform,
            source_url=final_url or original_url,
            extracted_keywords=hits,
            raw_payload={
                "content_type": SOCIAL_CLUE_CONTENT_TYPE,
                "source_method": "link_inbox",
                "platform": platform,
                "source_name": source_name,
                "original_url": original_url,
                "final_url": final_url,
                "summary": summary,
                "published_at": parsed_published_at.isoformat() if parsed_published_at else None,
                "crawled_at": datetime.utcnow().isoformat(),
                "verification_status": "time_verified" if parsed_published_at else "time_pending",
                "requires_verification": True,
                "confidence_level": confidence_label,
                "confidence_score": round(confidence_score, 3),
                "feedback_penalty": round(feedback_penalty, 3),
                "feedback_signals": feedback_signals,
                "mark_as_major": payload.mark_as_major,
                "recommended_action": "核实" if not parsed_published_at else "关注",
                "free_monitoring": True,
            },
        )
        db.add(event)
        db.flush()
        created += 1
        created_items.append(
            {
                "id": event.id,
                "title": event.event_title,
                "platform": platform,
                "source_url": event.source_url,
                "published_at": parsed_published_at.isoformat() if parsed_published_at else None,
                "verification_status": event.raw_payload["verification_status"],
                "keywords": hits,
                "confidence_level": confidence_label,
            }
        )
    audit(db, actor, "monitors.link_inbox.import", "external_hot_events", payload={"created": created, "skipped": skipped})
    db.commit()
    return {"created": created, "skipped": skipped, "items": created_items}


def vectorize(text: str, size: int = 64) -> list[float]:
    vector = [0.0] * size
    tokens = re.findall(r"[\w\u4e00-\u9fff]+", text.lower())
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        idx = digest[0] % size
        vector[idx] += 1.0
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [round(v / norm, 6) for v in vector]


def search_terms(text: str) -> list[str]:
    raw = re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]+", text.lower())
    terms: list[str] = []
    for token in raw:
        if re.fullmatch(r"[\u4e00-\u9fff]+", token):
            if len(token) <= 2:
                terms.append(token)
            else:
                terms.append(token)
                terms.extend(token[idx : idx + 2] for idx in range(len(token) - 1))
                terms.extend(token[idx : idx + 3] for idx in range(len(token) - 2))
        else:
            terms.append(token)
    terms.extend(extract_tags(text))
    deduped: list[str] = []
    for term in terms:
        if term and term not in deduped:
            deduped.append(term)
    return deduped


def lexical_score(query: str, article: models.HistoricalArticle) -> float:
    haystack_title = article.title.lower()
    haystack_summary = article.summary.lower()
    haystack_body = article.body.lower()
    haystack_tags = " ".join(article.tags).lower()
    terms = search_terms(query)
    if not terms:
        return 0.0
    score = 0.0
    for term in terms:
        if term in haystack_title:
            score += 0.22
        if term in haystack_summary:
            score += 0.12
        if term in haystack_tags:
            score += 0.12
        if term in haystack_body:
            score += 0.06
    if query and query.lower() in f"{haystack_title} {haystack_summary} {haystack_body}":
        score += 0.25
    return min(1.0, score)


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    return float(sum(x * y for x, y in zip(a, b)))


def import_articles(db: Session, items: list[ArticleImportItem], actor: str) -> int:
    count = 0
    for item in items:
        title_key = item.title.strip()
        exists = db.scalars(
            select(models.HistoricalArticle)
            .where(models.HistoricalArticle.account_name == item.account_name)
            .where(models.HistoricalArticle.title == title_key)
        ).first()
        if exists:
            continue
        risk = infer_risk(f"{item.title} {item.body}")
        tags = extract_tags(item.body, item.title)
        summary = item.summary or summarize(item.body)
        article = models.HistoricalArticle(
            account_name=item.account_name,
            title=title_key,
            body=item.body,
            published_at=item.published_at,
            summary=summary,
            source_url=item.source_url or "",
            column_name=item.column_name or infer_column(item.account_name, item.title + item.body),
            risk_level=risk,
            reusable_level="可系列化" if item.reads >= 10000 else "可翻新",
            tags=tags,
        )
        db.add(article)
        db.flush()
        db.add(
            models.ArticleMetric(
                article_id=article.id,
                reads=item.reads,
                likes=item.likes,
                wows=item.wows,
                favorites=item.favorites,
                shares=item.shares,
                comments=item.comments,
            )
        )
        for tag in tags:
            db.add(models.ArticleTag(article_id=article.id, tag_type="关键词", value=tag))
        db.add(models.ArticleEmbedding(article_id=article.id, vector=vectorize(item.title + " " + item.body)))
        count += 1
    audit(db, actor, "articles.import", "historical_articles", payload={"count": count})
    db.commit()
    return count


def parse_csv_articles(content: str) -> list[ArticleImportItem]:
    reader = csv.DictReader(io.StringIO(content))
    items: list[ArticleImportItem] = []
    for row in reader:
        items.append(
            ArticleImportItem(
                account_name=row.get("account_name") or row.get("公众号") or infer_account(row.get("title", ""), row.get("body", "")),
                title=row.get("title") or row.get("标题") or "未命名文章",
                body=row.get("body") or row.get("正文") or "",
                summary=row.get("summary") or row.get("摘要") or None,
                source_url=row.get("source_url") or row.get("链接") or None,
                column_name=row.get("column_name") or row.get("栏目") or None,
                reads=int(row.get("reads") or row.get("阅读量") or 0),
            )
        )
    return items


def parse_html_article(content: str, account_name: str = "募格学术") -> ArticleImportItem:
    soup = BeautifulSoup(content, "html.parser")
    title = soup.title.string if soup.title else summarize(soup.get_text(" "), 40)
    body = soup.get_text("\n")
    return ArticleImportItem(account_name=account_name, title=title or "HTML 导入文章", body=body)


def search_articles(db: Session, q: str, account: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
    query_vector = vectorize(q)
    stmt = select(models.HistoricalArticle, models.ArticleEmbedding.vector).outerjoin(
        models.ArticleEmbedding, models.HistoricalArticle.id == models.ArticleEmbedding.article_id
    )
    if account:
        stmt = stmt.where(models.HistoricalArticle.account_name == account)
    rows = db.execute(stmt).all()
    results = []
    for article, vector in rows:
        vector_score = cosine(query_vector, vector or [])
        text_score = lexical_score(q, article)
        score = max(vector_score, text_score, min(1.0, vector_score * 0.45 + text_score * 0.75))
        if score <= 0 and q:
            continue
        results.append(
            {
                "id": article.id,
                "title": article.title,
                "account_name": article.account_name,
                "summary": article.summary,
                "score": round(score, 4),
                "tags": article.tags,
                "risk_level": article.risk_level,
                "reusable_level": article.reusable_level,
                "source_url": article.source_url,
            }
        )
    results.sort(key=lambda x: x["score"], reverse=True)
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in results:
        key = (str(item["account_name"]), str(item["title"]).strip())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
        if len(deduped) >= limit:
            break
    return deduped


def refresh_article_to_topic(
    db: Session,
    article_id: int,
    actor: str,
    target_account: str | None = None,
    column_name: str | None = None,
) -> models.Topic:
    article = db.get(models.HistoricalArticle, article_id)
    if not article:
        raise ValueError("Article not found")
    account = target_account or article.account_name
    topic_title = f"{summarize(article.title, 64)}：现在还值得关注什么"
    existing = db.scalars(
        select(models.Topic)
        .where(models.Topic.title == topic_title)
        .where(models.Topic.target_account == account)
    ).first()
    if existing:
        return existing
    topic = models.Topic(
        title=topic_title,
        target_account=account,
        column_name=column_name or article.column_name or infer_column(account, article.title + article.body),
        angle_description="基于历史文章表现和当前读者需求，做一次更新、避坑或清单式翻新。",
        recommendation_reason=f"源自历史文章《{article.title}》，可复用原有结构，并补充最新政策、数据和案例。",
        risk_level=article.risk_level,
        status=models.TopicStatus.candidate,
        historical_reference_ids=[article.id],
        recommended_publish_at=datetime.utcnow() + timedelta(days=2),
    )
    db.add(topic)
    db.flush()
    db.add(models.TopicScore(topic_id=topic.id, **score_topic(topic.title, topic.risk_level, topic.target_account)))
    audit(db, actor, "articles.refresh_topic", "historical_articles", str(article_id), {"topic_id": topic.id})
    db.commit()
    return topic


def run_monitors(db: Session, manual_events: list[str], actor: str) -> tuple[int, int]:
    ensure_default_monitor_sources(db)
    hot_count = 0
    academic_count = 0
    sources = db.scalars(select(models.MonitorSource).where(models.MonitorSource.enabled.is_(True))).all()
    for source in sources:
        if source.source_type == "html_list":
            fetched_items = fetch_html_list_items(source)
        elif source.source_type == "wechat_account":
            fetched_items = fetch_wechat_account_items(db, source)
        else:
            fetched_items = fetch_rss_items(source)
        for rss_item in fetched_items:
            title = rss_item["title"]
            source_url = rss_item.get("link", "")
            summary = rss_item.get("summary") or source.notes
            published_at = parse_source_datetime(rss_item.get("published", ""))
            source_name = rss_item.get("source_name") or source.name
            text_for_filter = f"{title} {summary} {source.name} {source_name}"
            if source.name in STRICT_ENGLISH_SOURCES:
                if not within_hours(published_at, ENGLISH_NEWS_WINDOW_HOURS):
                    continue
                if _existing_academic_item(db, title, source_url):
                    continue
                risk = models.RiskLevel.high if "retraction" in source.name.lower() or infer_risk(title) == models.RiskLevel.high else models.RiskLevel.medium
                translated_title = LLMClient().text_chat(
                    system="把英文科研资讯标题翻译成简洁中文，只输出标题。",
                    user=title,
                    fallback=title,
                )
                translated_summary = LLMClient().text_chat(
                    system="把科研资讯摘要整理成适合中文公众号编辑看的 80 字以内中文摘要。无法确认的事实要提示核实。",
                    user=f"标题：{title}\n摘要：{summary}",
                    fallback=summarize(summary or title, 120),
                )
                db.add(
                    models.AcademicMonitorItem(
                        source_platform=source.name,
                        original_title=title,
                        translated_title=translated_title,
                        translated_summary=translated_summary,
                        source_url=source_url,
                        risk_level=risk,
                        raw_payload={
                            "published_at": published_at.isoformat(),
                            "crawled_at": datetime.utcnow().isoformat(),
                            "source_name": source_name,
                            "source_type": source.source_type,
                            "source_summary": summary,
                            "time_window_hours": ENGLISH_NEWS_WINDOW_HOURS,
                        },
                    )
                )
                academic_count += 1
                continue

            hits = keyword_hits(text_for_filter, STRICT_CHINESE_MONITOR_KEYWORDS)
            if not hits:
                continue
            if not within_hours(published_at, DOMESTIC_NEWS_WINDOW_HOURS):
                continue
            if _existing_hot_event(db, title, source_url):
                continue
            risk = infer_risk(text_for_filter)
            heat = 45 + min(35, len(hits) * 7)
            if risk == models.RiskLevel.high:
                heat += 15
            event = models.ExternalHotEvent(
                event_title=title,
                heat_index=min(100, heat),
                source_platform=source_name or source.name,
                source_url=source_url,
                extracted_keywords=hits,
                raw_payload={
                    "published_at": published_at.isoformat(),
                    "crawled_at": datetime.utcnow().isoformat(),
                    "configured_source": source.name,
                    "source_name": source_name,
                    "summary": summary,
                    "risk_level": risk.value,
                    "time_window_hours": DOMESTIC_NEWS_WINDOW_HOURS,
                },
            )
            db.add(event)
            hot_count += 1
    manual_count = len([item for item in manual_events if item.strip()])
    audit(db, actor, "monitors.run", "monitor", payload={"hot": hot_count, "academic": academic_count, "manual_ignored": manual_count})
    db.commit()
    return hot_count, academic_count


def _topic_from_monitor(
    db: Session,
    title: str,
    target_account: str,
    angle: str,
    reason: str,
    risk: models.RiskLevel,
    actor: str,
    item_type: str,
    item_id: int,
    column_name: str | None = None,
) -> models.Topic:
    existing = db.scalars(
        select(models.MonitorConversion).where(
            models.MonitorConversion.item_type == item_type,
            models.MonitorConversion.item_id == item_id,
        )
    ).first()
    if existing:
        topic = db.get(models.Topic, existing.topic_id)
        if topic:
            return topic
    refs = [r["id"] for r in search_articles(db, title, account=target_account, limit=3)]
    topic = models.Topic(
        title=title,
        target_account=target_account,
        column_name=column_name or infer_column(target_account, title),
        angle_description=angle,
        recommendation_reason=reason,
        risk_level=risk,
        historical_reference_ids=refs,
        source_event_id=item_id if item_type == "hot_event" else -item_id,
        recommended_publish_at=datetime.utcnow() + timedelta(days=1),
    )
    db.add(topic)
    db.flush()
    db.add(models.TopicScore(topic_id=topic.id, **score_topic(topic.title, topic.risk_level, topic.target_account)))
    db.add(models.MonitorConversion(item_type=item_type, item_id=item_id, topic_id=topic.id, actor=actor))
    audit(db, actor, "monitors.convert", item_type, str(item_id), {"topic_id": topic.id})
    db.commit()
    return topic


def convert_hot_event_to_topic(
    db: Session,
    event_id: int,
    actor: str,
    target_account: str | None = None,
    column_name: str | None = None,
) -> models.Topic:
    event = db.get(models.ExternalHotEvent, event_id)
    if not event:
        raise ValueError("Hot event not found")
    account = target_account or infer_account(event.event_title, " ".join(event.extracted_keywords))
    risk = infer_risk(event.event_title)
    published_at = hot_event_published_at(event)
    return _topic_from_monitor(
        db,
        title=event.event_title if account == "募格学术" else f"{event.event_title}对博士求职有什么影响",
        target_account=account,
        angle="从热点事件拆解目标读者关心的背景、机会、风险和行动建议。",
        reason=f"来自监控热点：{event.source_platform}；发布时间：{format_dt(published_at)}；抓取时间：{format_dt(event.created_at)}；热度 {event.heat_index}。",
        risk=risk,
        actor=actor,
        item_type="hot_event",
        item_id=event.id,
        column_name=column_name,
    )


def convert_academic_item_to_topic(
    db: Session,
    item_id: int,
    actor: str,
    target_account: str | None = None,
    column_name: str | None = None,
) -> models.Topic:
    item = db.get(models.AcademicMonitorItem, item_id)
    if not item:
        raise ValueError("Academic monitor item not found")
    account = target_account or "募格学术"
    title = item.translated_title or item.original_title
    published_at = academic_item_published_at(item)
    topic = _topic_from_monitor(
        db,
        title=title,
        target_account=account,
        angle="从学术前沿、科研规范或科研生态角度转化为中文公众号选题。",
        reason=f"来自监控热点：{item.source_platform}；发布时间：{format_dt(published_at)}；抓取时间：{format_dt(item.created_at)}；需核实原始来源。",
        risk=item.risk_level,
        actor=actor,
        item_type="academic_item",
        item_id=item.id,
        column_name=column_name,
    )
    item.status = "CONVERTED"
    db.commit()
    return topic


def add_wechat_monitor_accounts(db: Session, accounts: list[WechatMonitorAccountItem], actor: str) -> int:
    ensure_default_monitor_sources(db)
    count = 0
    existing = set(db.scalars(select(models.MonitorSource.name)).all())
    for account in accounts:
        source_name = f"微信公众号-{account.name}"
        if source_name in existing:
            continue
        db.add(
            models.MonitorSource(
                name=source_name,
                source_type="wechat_account",
                url=account.wechat_id or "",
                enabled=True,
                credibility_level="微信公众号公开文章",
                account_bias="募格学术",
                keywords=account.keywords or ["学术", "科研"],
                notes=account.notes or "微信公众号源：需通过手动文章链接、RSSHub/WeWe-RSS 或授权数据源导入文章。",
            )
        )
        existing.add(source_name)
        count += 1
    audit(db, actor, "monitors.wechat_accounts.batch", "monitor_sources", payload={"count": count})
    db.commit()
    return count


def import_wechat_monitor_articles(db: Session, items: list[WechatArticleMonitorItem], actor: str) -> int:
    ensure_monitor_schema(db)
    count = 0
    for item in items:
        platform = f"微信公众号:{item.account_name}"
        if item.url and _existing_academic_item(db, item.title, item.url):
            continue
        if not item.url and _existing_academic_item(db, item.title):
            continue
        text = f"{item.title} {item.summary} {' '.join(item.keywords)}"
        risk = infer_risk(text)
        db.add(
            models.AcademicMonitorItem(
                source_platform=platform,
                original_title=item.title,
                translated_title=item.title,
                translated_summary=item.summary or f"来自 {item.account_name} 的微信公众号文章，建议人工核实原文后转选题。",
                source_url=item.url,
                risk_level=risk,
                status="UNREAD",
            )
        )
        count += 1
    audit(db, actor, "monitors.wechat_articles.import", "academic_monitor_items", payload={"count": count})
    db.commit()
    return count


def score_topic(title: str, risk: models.RiskLevel, account: str) -> dict[str, float]:
    heat = 80 if any(k in title for k in ["基金", "招聘", "撤稿", "博士后"]) else 55
    account_match = 85 if infer_account(title, title) == account else 68
    freshness = 75
    penalty = {"low": 0, "medium": 12, "high": 28}[risk.value]
    total = round((heat * 0.35 + account_match * 0.35 + freshness * 0.2 - penalty) / 100, 3)
    return {"heat": heat, "account_match": account_match, "freshness": freshness, "risk_penalty": penalty, "total": total}


def normalize_topic_title(title: str) -> str:
    text = re.sub(r"\s+", "", title.lower())
    text = re.sub(r"[：:，,。！？!?、“”\"'《》（）()【】\\[\\]-]", "", text)
    for suffix in ["背后的科研生态观察", "对博士求职和高校岗位选择有什么影响", "现在还值得关注什么"]:
        text = text.replace(suffix, "")
    return text[:80]


def _topic_exists(db: Session, title: str, account: str, seen: set[tuple[str, str]]) -> bool:
    key = (account, normalize_topic_title(title))
    if key in seen:
        return True
    existing = db.scalars(select(models.Topic).where(models.Topic.target_account == account)).all()
    for topic in existing:
        if normalize_topic_title(topic.title) == key[1]:
            seen.add(key)
            return True
    return False


def _topic_candidates_from_seed(raw: str, source: str) -> list[dict[str, str]]:
    base = summarize(raw, 64).strip(" ：:，,。")
    if not base:
        return []
    return [
        {
            "account": "募格学术",
            "title": f"{base}：科研群体需要核实的事实与影响",
            "angle": "围绕已监控到的新闻事实、来源可靠性、科研生态影响和读者行动建议展开。",
            "reason": f"来自真实监控热点：{source}。",
        },
        {
            "account": "募格学术",
            "title": f"从{base}看科研评价和学术规范的新变化",
            "angle": "只基于监控新闻做延展，避免把历史经验当成当日热点。",
            "reason": f"来自真实监控热点：{source}。",
        },
        {
            "account": "募格科聘",
            "title": f"{base}会影响博士、博士后和青年教师的哪些选择",
            "angle": "从求职、岗位判断、职业路径和信息核实角度切入，但必须回到原新闻和官方信息核验。",
            "reason": f"来自真实监控热点：{source}。",
        },
        {
            "account": "募格科聘",
            "title": f"围绕{base}，高校人才求职者要提前问清什么",
            "angle": "聚焦岗位条件、待遇承诺、编制、截止时间和官方来源核验。",
            "reason": f"来自真实监控热点：{source}。",
        },
    ]


def generate_topics(db: Session, seed: str | None, count_per_account: int, actor: str) -> list[models.Topic]:
    seed_sources: list[tuple[str, str, str, int]] = []
    hot_events, academic_items = monitor_result_candidates(db, 20, 10)
    seed_sources.extend(
        (
            event.event_title,
            f"{event.source_platform} / 发布时间 {format_dt(hot_event_published_at(event))} / 抓取 {format_dt(event.created_at)}",
            "hot_event",
            event.id,
        )
        for event in hot_events
    )
    seed_sources.extend(
        (
            item.translated_title,
            f"{item.source_platform} / 发布时间 {format_dt(academic_item_published_at(item))} / 抓取 {format_dt(item.created_at)}",
            "academic_item",
            item.id,
        )
        for item in academic_items
    )
    generated: list[models.Topic] = []
    seen: set[tuple[str, str]] = set()
    for raw, source, item_type, item_id in seed_sources:
        for candidate in _topic_candidates_from_seed(raw, source):
            account = candidate["account"]
            if len([topic for topic in generated if topic.target_account == account]) >= count_per_account:
                continue
            title = candidate["title"]
            if _topic_exists(db, title, account, seen):
                continue
            seen.add((account, normalize_topic_title(title)))
            risk = infer_risk(title)
            refs = [r["id"] for r in search_articles(db, title, account=account, limit=3)]
            topic = models.Topic(
                title=title,
                target_account=account,
                column_name=infer_column(account, title),
                angle_description=candidate["angle"],
                recommendation_reason=candidate["reason"],
                risk_level=risk,
                historical_reference_ids=refs,
                source_event_id=item_id if item_type == "hot_event" else -item_id,
                recommended_publish_at=datetime.utcnow() + timedelta(days=len(generated) + 1),
            )
            db.add(topic)
            db.flush()
            scores = score_topic(title, risk, account)
            db.add(models.TopicScore(topic_id=topic.id, **scores))
            db.add(models.MonitorConversion(item_type=item_type, item_id=item_id, topic_id=topic.id, actor=actor))
            generated.append(topic)
        if all(len([topic for topic in generated if topic.target_account == account]) >= count_per_account for account in ["募格学术", "募格科聘"]):
            break
    audit(db, actor, "topics.generate", "topics", payload={"count": len(generated)})
    db.commit()
    return generated


def select_pushable_topics(db: Session, limit: int | None = None, threshold: float | None = None) -> list[tuple[models.Topic, float]]:
    auto_settings = automation.get_raw_settings(db)
    topic_limit = limit or int(auto_settings.get("push_topic_limit") or get_settings().monitor_push_topic_limit)
    score_threshold = threshold if threshold is not None else float(auto_settings.get("push_score_threshold") or get_settings().monitor_push_score_threshold)
    rows = db.execute(
        select(models.Topic, models.TopicScore.total)
        .join(models.TopicScore, models.Topic.id == models.TopicScore.topic_id)
        .where(models.Topic.status == models.TopicStatus.candidate)
        .where(models.Topic.risk_level != models.RiskLevel.high)
        .where(models.TopicScore.total >= score_threshold)
        .order_by(models.TopicScore.total.desc(), models.Topic.updated_at.desc())
        .limit(topic_limit)
    ).all()
    return [(topic, float(score or 0)) for topic, score in rows]


def topic_source_info(db: Session, topic: models.Topic) -> dict[str, Any] | None:
    conversion = db.scalars(select(models.MonitorConversion).where(models.MonitorConversion.topic_id == topic.id)).first()
    item_type = conversion.item_type if conversion else ("hot_event" if (topic.source_event_id or 0) > 0 else "academic_item")
    item_id = conversion.item_id if conversion else abs(topic.source_event_id or 0)
    if not item_id:
        return None
    if item_type == "hot_event":
        item = db.get(models.ExternalHotEvent, item_id)
        if not item:
            return None
        return {
            "item_type": "hot_event",
            "item_id": item.id,
            "title": item.event_title,
            "source": item.source_platform,
            "source_url": item.source_url,
            "published_at": hot_event_published_at(item).isoformat() if hot_event_published_at(item) else None,
            "crawled_at": item.created_at.isoformat() if item.created_at else None,
            "valid": is_valid_hot_event(item),
        }
    item = db.get(models.AcademicMonitorItem, item_id)
    if not item:
        return None
    return {
        "item_type": "academic_item",
        "item_id": item.id,
        "title": item.translated_title or item.original_title,
        "source": item.source_platform,
        "source_url": item.source_url,
        "published_at": academic_item_published_at(item).isoformat() if academic_item_published_at(item) else None,
        "crawled_at": item.created_at.isoformat() if item.created_at else None,
        "valid": is_valid_academic_item(item),
    }


def cleanup_unsupported_topics(db: Session, actor: str = "system") -> dict[str, int]:
    inspected = 0
    discarded = 0
    for topic in db.scalars(select(models.Topic).where(models.Topic.status != models.TopicStatus.discarded)).all():
        inspected += 1
        source_info = topic_source_info(db, topic)
        if source_info and source_info.get("valid"):
            continue
        topic.status = models.TopicStatus.discarded
        if "无有效监控热点支撑" not in topic.recommendation_reason:
            topic.recommendation_reason = f"{topic.recommendation_reason}\n[系统自检] 无有效监控热点支撑，已标记为放弃。"
        discarded += 1
    audit(db, actor, "topics.cleanup_unsupported", "topics", payload={"inspected": inspected, "discarded": discarded})
    db.commit()
    return {"inspected": inspected, "discarded": discarded}


def record_monitor_feedback(db: Session, item_type: str, item_id: int, reason: str, note: str, actor: str) -> dict[str, Any]:
    payload = {
        "reason": reason,
        "note": note,
        "actor": actor,
        "created_at": datetime.utcnow().isoformat(),
    }
    if item_type in {"hot_event", "social_clue"}:
        item = db.get(models.ExternalHotEvent, item_id)
        if not item:
            raise ValueError("Hot event not found")
        raw = dict(item.raw_payload) if isinstance(item.raw_payload, dict) else {}
        raw["feedback"] = payload
        raw["hidden_by_feedback"] = True
        item.raw_payload = raw
    elif item_type == "academic_item":
        item = db.get(models.AcademicMonitorItem, item_id)
        if not item:
            raise ValueError("Academic monitor item not found")
        raw = dict(getattr(item, "raw_payload", {})) if isinstance(getattr(item, "raw_payload", {}), dict) else {}
        raw["feedback"] = payload
        raw["hidden_by_feedback"] = True
        item.raw_payload = raw
        item.status = "REJECTED"
    else:
        raise ValueError("Unsupported monitor item type")
    audit(db, actor, "monitors.feedback", item_type, str(item_id), payload)
    db.commit()
    return {"ok": True, "item_type": item_type, "item_id": item_id}


def record_topic_feedback(db: Session, topic_id: int, reason: str, note: str, actor: str) -> dict[str, Any]:
    topic = db.get(models.Topic, topic_id)
    if not topic:
        raise ValueError("Topic not found")
    topic.status = models.TopicStatus.discarded
    topic.recommendation_reason = f"{topic.recommendation_reason}\n[用户反馈] {reason}：{note}".strip()
    audit(db, actor, "topics.feedback", "topics", str(topic_id), {"reason": reason, "note": note})
    db.commit()
    return {"ok": True, "topic_id": topic_id}


def render_dingtalk_topics(topics: list[tuple[models.Topic, float]]) -> str:
    if not topics:
        return "### 募格监控提醒\n\n本轮监控暂未发现达到推送阈值的候选选题。"
    lines = ["### 募格监控发现候选选题", "", f"共筛出 {len(topics)} 个候选选题：", ""]
    for idx, (topic, score) in enumerate(topics, start=1):
        risk_label = {"low": "低风险", "medium": "中风险", "high": "高风险"}[topic.risk_level.value]
        lines.extend(
            [
                f"**{idx}. {topic.title}**",
                f"- 账号：{topic.target_account}",
                f"- 栏目：{topic.column_name}",
                f"- 评分：{score:.2f}",
                f"- 风险：{risk_label}",
                f"- 理由：{topic.recommendation_reason}",
                "",
            ]
        )
    lines.append("> 请在后台“选题池 / 监控页”确认选题，AI 不会自动发布。")
    return "\n".join(lines)


def _already_pushed(db: Session, item_type: str, item_id: int, push_type: str) -> bool:
    return db.scalars(
        select(models.MonitorPushRecord.id).where(
            models.MonitorPushRecord.item_type == item_type,
            models.MonitorPushRecord.item_id == item_id,
            models.MonitorPushRecord.push_type == push_type,
        )
    ).first() is not None


def judge_breaking_news(
    db: Session,
    item_type: str,
    item_id: int,
    title: str,
    summary: str,
    heat_index: int,
    risk_level: models.RiskLevel,
) -> dict[str, Any]:
    settings = automation.get_raw_settings(db)
    if not settings.get("breaking_news_enabled", True):
        return {"is_breaking": False, "reason": "breaking news push disabled", "score": 0}
    keywords = [str(item).strip() for item in settings.get("breaking_news_keywords", []) if str(item).strip()]
    keyword_hits = [keyword for keyword in keywords if keyword in f"{title} {summary}"]
    score = 0
    score += min(45, len(keyword_hits) * 15)
    if heat_index >= int(settings.get("breaking_news_min_heat") or 85):
        score += 35
    if risk_level == models.RiskLevel.high:
        score += 15
    elif risk_level == models.RiskLevel.medium:
        score += 8
    fallback = {
        "is_breaking": score >= 45,
        "score": score,
        "reason": f"关键词命中：{','.join(keyword_hits) or '无'}；热度：{heat_index}；风险：{risk_level.value}",
    }
    llm_result = LLMClient().json_chat(
        system=(
            "你是公众号运营监控助手。只输出 JSON："
            "{\"is_breaking\":true/false,\"score\":0-100,\"reason\":\"...\"}。"
            "请根据用户给出的重大新闻标准判断是否需要立即单独推送。"
        ),
        user=(
            f"重大新闻标准：{settings.get('breaking_news_llm_criteria')}\n"
            f"标题：{title}\n摘要：{summary}\n热度：{heat_index}\n风险：{risk_level.value}\n"
            f"规则初判：{fallback}"
        ),
        fallback=fallback,
    )
    is_breaking = bool(llm_result.get("is_breaking", fallback["is_breaking"])) or fallback["is_breaking"]
    final_score = max(float(llm_result.get("score") or 0), float(fallback["score"]))
    return {
        "is_breaking": is_breaking and final_score >= 45,
        "score": final_score,
        "reason": str(llm_result.get("reason") or fallback["reason"]),
        "keyword_hits": keyword_hits,
        "item_type": item_type,
        "item_id": item_id,
    }


def render_breaking_news_markdown(title: str, summary: str, source: str, judgment: dict[str, Any]) -> str:
    return "\n".join(
        [
            "### 募格监控：重大新闻提醒",
            "",
            f"**{title}**",
            "",
            f"- 来源：{source}",
            f"- 重大程度：{float(judgment.get('score') or 0):.0f}/100",
            f"- 判断理由：{judgment.get('reason')}",
            "",
            summary or "建议尽快查看原始来源并判断是否转选题。",
            "",
            "> 这是一条即时提醒；仍需人工核实，不会自动发布。",
        ]
    )


def _payload_datetime(payload: dict[str, Any] | None, key: str = "published_at") -> datetime | None:
    if not isinstance(payload, dict):
        return None
    value = payload.get(key)
    if not value:
        return None
    return parse_source_datetime(str(value))


def hot_event_published_at(item: models.ExternalHotEvent) -> datetime | None:
    return _payload_datetime(item.raw_payload)


def academic_item_published_at(item: models.AcademicMonitorItem) -> datetime | None:
    return _payload_datetime(getattr(item, "raw_payload", {}) or {})


def is_valid_hot_event(item: models.ExternalHotEvent) -> bool:
    if isinstance(item.raw_payload, dict) and item.raw_payload.get("hidden_by_feedback"):
        return False
    if not within_hours(hot_event_published_at(item), DOMESTIC_NEWS_WINDOW_HOURS):
        return False
    text_value = f"{item.event_title} {' '.join(item.extracted_keywords)} {item.raw_payload.get('summary', '') if isinstance(item.raw_payload, dict) else ''}"
    return bool(keyword_hits(text_value, STRICT_CHINESE_MONITOR_KEYWORDS))


def is_valid_academic_item(item: models.AcademicMonitorItem) -> bool:
    raw = getattr(item, "raw_payload", {}) or {}
    if isinstance(raw, dict) and raw.get("hidden_by_feedback"):
        return False
    return item.source_platform in STRICT_ENGLISH_SOURCES and within_hours(academic_item_published_at(item), ENGLISH_NEWS_WINDOW_HOURS)


def is_social_clue(item: models.ExternalHotEvent) -> bool:
    raw = item.raw_payload if isinstance(item.raw_payload, dict) else {}
    return raw.get("content_type") == SOCIAL_CLUE_CONTENT_TYPE


def social_clue_candidates(db: Session, limit: int = 30) -> list[models.ExternalHotEvent]:
    items = [
        item
        for item in db.scalars(select(models.ExternalHotEvent).order_by(models.ExternalHotEvent.id.desc()).limit(300)).all()
        if is_social_clue(item) and not (isinstance(item.raw_payload, dict) and item.raw_payload.get("hidden_by_feedback"))
    ]
    items.sort(key=lambda item: (item.heat_index, item.created_at or datetime.min), reverse=True)
    return items[:limit]


def feedback_items(db: Session, limit: int = 30) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in db.scalars(select(models.ExternalHotEvent).order_by(models.ExternalHotEvent.updated_at.desc()).limit(300)).all():
        raw = item.raw_payload if isinstance(item.raw_payload, dict) else {}
        feedback = raw.get("feedback")
        if not isinstance(feedback, dict):
            continue
        rows.append(
            {
                "item_type": "social_clue" if is_social_clue(item) else "hot_event",
                "id": item.id,
                "title": item.event_title,
                "source": item.source_platform,
                "source_url": item.source_url,
                "reason": feedback.get("reason", ""),
                "note": feedback.get("note", ""),
                "actor": feedback.get("actor", ""),
                "created_at": feedback.get("created_at"),
            }
        )
    for item in db.scalars(select(models.AcademicMonitorItem).order_by(models.AcademicMonitorItem.updated_at.desc()).limit(300)).all():
        raw = getattr(item, "raw_payload", {}) if isinstance(getattr(item, "raw_payload", {}), dict) else {}
        feedback = raw.get("feedback")
        if not isinstance(feedback, dict):
            continue
        rows.append(
            {
                "item_type": "academic_item",
                "id": item.id,
                "title": item.translated_title or item.original_title,
                "source": item.source_platform,
                "source_url": item.source_url,
                "reason": feedback.get("reason", ""),
                "note": feedback.get("note", ""),
                "actor": feedback.get("actor", ""),
                "created_at": feedback.get("created_at"),
            }
        )
    rows.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return rows[:limit]


def format_dt(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%M") if value else "未知"


def monitor_result_candidates(db: Session, hot_limit: int = 20, academic_limit: int = 10) -> tuple[list[models.ExternalHotEvent], list[models.AcademicMonitorItem]]:
    ensure_monitor_schema(db)
    hot_events = [
        item
        for item in db.scalars(select(models.ExternalHotEvent).order_by(models.ExternalHotEvent.id.desc()).limit(200)).all()
        if is_valid_hot_event(item)
    ]
    academic_items = [
        item
        for item in db.scalars(select(models.AcademicMonitorItem).order_by(models.AcademicMonitorItem.id.desc()).limit(200)).all()
        if is_valid_academic_item(item)
    ]
    hot_events.sort(key=lambda item: (item.heat_index, hot_event_published_at(item) or datetime.min), reverse=True)
    academic_items.sort(key=lambda item: (academic_item_published_at(item) or datetime.min), reverse=True)
    return hot_events[:hot_limit], academic_items[:academic_limit]


def render_monitor_digest_markdown(
    hot_events: list[models.ExternalHotEvent],
    academic_items: list[models.AcademicMonitorItem],
    social_clues: list[models.ExternalHotEvent] | None = None,
) -> str:
    social_clues = social_clues or []
    if not hot_events and not academic_items and not social_clues:
        return "### 募格监控结果\n\n本轮没有符合硬性条件的新增新闻，也没有新的公开链接收件箱线索。"
    lines = ["### 募格监控结果", "", "以下为本轮保留的第一手热点新闻线索，不是 AI 生成选题。", ""]
    if hot_events:
        lines.extend(["#### 中文新闻", ""])
        for idx, item in enumerate(hot_events[:10], start=1):
            published_at = hot_event_published_at(item)
            summary = item.raw_payload.get("summary", "") if isinstance(item.raw_payload, dict) else ""
            lines.extend(
                [
                    f"**{idx}. {item.event_title}**",
                    f"- 来源：{item.source_platform}",
                    f"- 发布时间：{format_dt(published_at)}",
                    f"- 关键词：{'、'.join(item.extracted_keywords)}",
                    f"- 重要性：{item.heat_index}/100",
                    f"- 链接：{item.source_url or '无'}",
                    f"- 摘要：{summarize(summary, 120) if summary else '暂无摘要，请打开原文核实。'}",
                    "",
                ]
            )
    if academic_items:
        lines.extend(["#### 英文学术前沿", ""])
        for idx, item in enumerate(academic_items[:5], start=1):
            published_at = academic_item_published_at(item)
            lines.extend(
                [
                    f"**{idx}. {item.translated_title}**",
                    f"- 来源：{item.source_platform}",
                    f"- 发布时间：{format_dt(published_at)}",
                    f"- 原题：{item.original_title}",
                    f"- 链接：{item.source_url or '无'}",
                    f"- 摘要：{item.translated_summary}",
                    "",
                ]
            )
    if social_clues:
        lines.extend(["#### 社交平台线索（待核实）", ""])
        for idx, item in enumerate(social_clues[:8], start=1):
            raw = item.raw_payload if isinstance(item.raw_payload, dict) else {}
            published_at = hot_event_published_at(item)
            lines.extend(
                [
                    f"**{idx}. {item.event_title}**",
                    f"- 平台：{item.source_platform}",
                    f"- 来源：{raw.get('source_name') or item.source_platform}",
                    f"- 发布时间：{format_dt(published_at)}",
                    f"- 核实状态：{'发布时间待核实' if not published_at else '已解析发布时间，仍需核实事实'}",
                    f"- 关键词：{'、'.join(item.extracted_keywords) if item.extracted_keywords else '未命中，人工报料待判断'}",
                    f"- 可信度：{raw.get('confidence_level', 'medium')}",
                    f"- 推荐动作：{raw.get('recommended_action', '核实')}",
                    f"- 链接：{item.source_url or '无'}",
                    "",
                ]
            )
    lines.append("> 如发现旧闻、来源错误或不符合关键词，请在后台监控页点“反馈不合格”，系统会记录并隐藏该条。")
    return "\n".join(lines)


def push_breaking_news_from_monitors(db: Session, actor: str = "scheduler") -> dict[str, Any]:
    settings = automation.get_raw_settings(db)
    if not automation.push_allowed_now(settings):
        return {"pushed": 0, "skipped": "quiet_hours"}
    pushed = 0
    notifier = DingTalkNotifier(settings)
    hot_events, academic_items = monitor_result_candidates(db, 40, 40)
    candidates: list[tuple[str, int, str, str, str, int, models.RiskLevel]] = []
    candidates.extend(
        ("hot_event", item.id, item.event_title, " ".join(item.extracted_keywords), item.source_platform, item.heat_index, infer_risk(item.event_title))
        for item in hot_events
    )
    candidates.extend(
        ("academic_item", item.id, item.translated_title, item.translated_summary, item.source_platform, 70, item.risk_level)
        for item in academic_items
    )
    candidates.extend(
        (
            "social_clue",
            item.id,
            item.event_title,
            item.raw_payload.get("summary", "") if isinstance(item.raw_payload, dict) else "",
            item.source_platform,
            item.heat_index,
            infer_risk(f"{item.event_title} {' '.join(item.extracted_keywords)}"),
        )
        for item in social_clue_candidates(db, 30)
        if isinstance(item.raw_payload, dict) and item.raw_payload.get("mark_as_major")
    )
    for item_type, item_id, title, summary, source, heat, risk in candidates:
        if _already_pushed(db, item_type, item_id, "breaking"):
            continue
        judgment = judge_breaking_news(db, item_type, item_id, title, summary, heat, risk)
        if not judgment["is_breaking"]:
            continue
        result = notifier.send_markdown("募格重大新闻提醒", render_breaking_news_markdown(title, summary, source, judgment))
        db.add(
            models.MonitorPushRecord(
                item_type=item_type,
                item_id=item_id,
                push_type="breaking",
                status="sent" if result.get("ok") else "failed",
                payload={"judgment": judgment, "push_result": result},
            )
        )
        pushed += 1 if result.get("ok") else 0
    audit(db, actor, "monitors.breaking_push", "monitor_push_records", payload={"pushed": pushed})
    db.commit()
    return {"pushed": pushed}


def run_monitor_pipeline(db: Session, actor: str = "scheduler") -> dict[str, Any]:
    auto_settings = automation.get_raw_settings(db)
    hot_count, academic_count = run_monitors(db, [], actor)
    breaking_result = push_breaking_news_from_monitors(db, actor)
    hot_events, academic_items = monitor_result_candidates(db)
    social_clues = social_clue_candidates(db, 10)
    markdown_text = render_monitor_digest_markdown(hot_events, academic_items, social_clues)
    if automation.push_allowed_now(auto_settings):
        push_result = DingTalkNotifier(auto_settings).send_markdown("募格监控新闻提醒", markdown_text)
    else:
        push_result = {"ok": False, "reason": "quiet_hours"}
    audit(
        db,
        actor,
        "monitors.pipeline",
        "monitor",
        payload={
            "hot_events_created": hot_count,
            "academic_items_created": academic_count,
            "monitor_items_pushed": len(hot_events) + len(academic_items) + len(social_clues),
            "breaking_result": breaking_result,
            "push_result": push_result,
        },
    )
    db.commit()
    return {
        "hot_events_created": hot_count,
        "academic_items_created": academic_count,
        "topics_generated": 0,
        "topics_pushed": 0,
        "monitor_items_pushed": len(hot_events) + len(academic_items) + len(social_clues),
        "breaking_result": breaking_result,
        "push_result": push_result,
    }


def log_prompt(db: Session, name: str, input_payload: dict, output_model: BaseModel) -> None:
    db.add(
        models.PromptRun(
            prompt_name=name,
            model="local-fallback",
            input_payload=input_payload,
            output_payload=output_model.model_dump(),
            validation_schema=output_model.__class__.__name__,
        )
    )


class GeneratedMaterialPack(BaseModel):
    background: str
    core_questions: list[str]
    key_points: list[str]
    sources: list[dict[str, Any]]
    risk_tips: list[str]
    writing_angle: str


def ensure_topic(db: Session, topic_id: int) -> models.Topic:
    topic = db.get(models.Topic, topic_id)
    if not topic:
        raise ValueError("Topic not found")
    return topic


def generate_material_pack(db: Session, topic_id: int, actor: str) -> models.MaterialPack:
    topic = ensure_topic(db, topic_id)
    references = search_articles(db, topic.title, account=topic.target_account, limit=3)
    output = GeneratedMaterialPack(
        background=f"{topic.title} 是一个适合 {topic.target_account} 的选题，需要结合目标读者的实际痛点展开。",
        core_questions=[
            "这个选题与目标读者的直接关系是什么？",
            "哪些事实必须核实来源？",
            "如何避免与历史文章重复？",
        ],
        key_points=[
            topic.angle_description,
            "优先使用官方公告、期刊原文或历史文章作为背景材料。",
            "避免绝对化、承诺式和未核实表述。",
        ],
        sources=[
            {"type": "historical_article", "id": item["id"], "title": item["title"], "url": item["source_url"]}
            for item in references
        ],
        risk_tips=["涉及高校、岗位、待遇、撤稿或具体人物时必须人工核实。"]
        if topic.risk_level != models.RiskLevel.low
        else ["常规事实仍需标注来源，避免大段复用历史文章。"],
        writing_angle=topic.angle_description,
    )
    llm_payload = LLMClient().json_chat(
        system=(
            "你是公众号内容运营中台的资料整理助手。只输出 JSON，字段必须包含 "
            "background, core_questions, key_points, sources, risk_tips, writing_angle。"
            "所有无法确认的事实必须写入 risk_tips。"
        ),
        user=(
            f"公众号：{topic.target_account}\n选题：{topic.title}\n角度：{topic.angle_description}\n"
            f"历史参考：{references}\n请生成适合编辑审核的资料包。"
        ),
        fallback=output.model_dump(),
    )
    output = GeneratedMaterialPack.model_validate(llm_payload)
    log_prompt(db, "material_pack", {"topic_id": topic_id, "title": topic.title}, output)
    pack = models.MaterialPack(topic_id=topic.id, **output.model_dump())
    db.add(pack)
    topic.status = models.TopicStatus.writing
    audit(db, actor, "workspace.material_pack", "topics", str(topic_id))
    db.commit()
    return pack


def generate_outline(db: Session, topic_id: int, actor: str) -> models.Outline:
    topic = ensure_topic(db, topic_id)
    sections = [
        {"heading": "一、为什么这个问题现在值得关注", "intent": "交代背景和读者痛点"},
        {"heading": "二、先把核心事实和限制条件说清楚", "intent": "列出来源、条件和不确定性"},
        {"heading": "三、从目标读者角度拆解选择", "intent": topic.angle_description},
        {"heading": "四、可执行建议和避坑提醒", "intent": "给出清单化建议"},
        {"heading": "五、结尾：回到理性判断", "intent": "避免煽动，提示继续关注"},
    ]
    llm_payload = LLMClient().json_chat(
        system="你是公众号主编。只输出 JSON，格式为 {\"sections\":[{\"heading\":\"...\",\"intent\":\"...\"}]}。",
        user=f"公众号：{topic.target_account}\n选题：{topic.title}\n角度：{topic.angle_description}\n请生成 5-7 段文章大纲。",
        fallback={"sections": sections},
    )
    if isinstance(llm_payload.get("sections"), list) and llm_payload["sections"]:
        sections = llm_payload["sections"]
    outline = models.Outline(topic_id=topic_id, sections=sections)
    db.add(outline)
    audit(db, actor, "workspace.outline", "topics", str(topic_id))
    db.commit()
    return outline


def generate_draft(db: Session, topic_id: int, actor: str) -> models.Draft:
    topic = ensure_topic(db, topic_id)
    outline = db.scalars(select(models.Outline).where(models.Outline.topic_id == topic_id).order_by(models.Outline.id.desc())).first()
    if not outline:
        outline = generate_outline(db, topic_id, actor)
    body_parts = [f"# {topic.title}", ""]
    for section in outline.sections:
        body_parts.append(f"## {section['heading']}")
        body_parts.append(f"{section['intent']}。这里建议编辑补充已核实来源，并结合 {topic.target_account} 的读者需求展开。")
        body_parts.append("")
    body_parts.append("本文为 AI 辅助初稿，涉及事实、引用、政策、招聘条件或争议信息时，请以官方来源和人工审核为准。")
    markdown_body = "\n".join(body_parts)
    markdown_body = LLMClient().text_chat(
        system=(
            "你是严谨的微信公众号编辑。输出 Markdown 初稿，不要编造来源，不要做绝对化结论；"
            "涉及高校、招聘、待遇、撤稿、政策时必须提醒人工核实。"
        ),
        user=f"公众号：{topic.target_account}\n选题：{topic.title}\n大纲：{outline.sections}\n请生成可供编辑修改的公众号初稿。",
        fallback=markdown_body,
    )
    draft = models.Draft(
        topic_id=topic_id,
        title=topic.title,
        body_markdown=markdown_body,
        body_html=markdown(markdown_body),
        status=models.DraftStatus.editing,
        citations=[{"note": "待编辑补充一手来源", "required": True}],
    )
    db.add(draft)
    audit(db, actor, "workspace.draft", "topics", str(topic_id))
    db.commit()
    return draft


def generate_titles(db: Session, topic_id: int, actor: str) -> list[models.TitleCandidate]:
    topic = ensure_topic(db, topic_id)
    templates = [
        "{title}",
        "{title}，这几个问题要先想清楚",
        "关于{short}，给科研人的一份理性提醒",
        "{short}：机会、风险和选择",
        "为什么{short}值得认真讨论",
        "{short}背后，真正影响你的是什么",
        "一文看懂{short}的关键判断",
        "{short}，不要只看表面信息",
        "从{short}看科研人的现实选择",
        "{short}之前，先核实这几件事",
    ]
    short = re.sub(r"[，。！？].*$", "", topic.title)[:24]
    llm_payload = LLMClient().json_chat(
        system=(
            "你是公众号标题编辑。只输出 JSON，格式为 "
            "{\"titles\":[{\"title\":\"...\",\"score\":0.88,\"risk_level\":\"low\"}],"
            "\"public_summary\":\"...\",\"share_text\":\"...\",\"cover_copy\":\"...\"}。"
            "标题必须避免恐吓、绝对化、未证实指控。"
        ),
        user=f"公众号：{topic.target_account}\n选题：{topic.title}\n请生成不少于 10 个候选标题并评分。",
        fallback={},
    )
    if isinstance(llm_payload.get("titles"), list) and len(llm_payload["titles"]) >= 10:
        templates = []
        for item in llm_payload["titles"][:12]:
            if isinstance(item, dict) and item.get("title"):
                templates.append(str(item["title"]))
    candidates = []
    for idx, template in enumerate(templates):
        text = template.format(title=topic.title, short=short) if "{" in template else template
        risk = infer_risk(text)
        score = max(0.45, 0.92 - idx * 0.035 - (0.12 if risk == models.RiskLevel.high else 0))
        candidate = models.TitleCandidate(
            topic_id=topic_id,
            title=text,
            score=round(score, 3),
            score_detail={
                "clarity": round(score + 0.02, 3),
                "click_potential": round(score, 3),
                "account_match": 0.86,
                "freshness": 0.78,
            },
            risk_level=risk,
        )
        db.add(candidate)
        candidates.append(candidate)
    db.add(
        models.Summary(
            topic_id=topic_id,
            public_summary=str(llm_payload.get("public_summary") or f"围绕“{short}”，梳理背景、关键判断和需要核实的风险点。"),
            share_text=str(llm_payload.get("share_text") or f"这篇稿件适合关注{topic.target_account}的读者收藏，尤其适合转给正在做选择的人。"),
            cover_copy=str(llm_payload.get("cover_copy") or short),
        )
    )
    audit(db, actor, "workspace.titles", "topics", str(topic_id))
    db.commit()
    return candidates


def risk_check(db: Session, topic_id: int, actor: str) -> list[models.RiskFinding]:
    draft = db.scalars(select(models.Draft).where(models.Draft.topic_id == topic_id).order_by(models.Draft.id.desc())).first()
    if not draft:
        draft = generate_draft(db, topic_id, actor)
    text = draft.title + "\n" + draft.body_markdown
    findings: list[models.RiskFinding] = []
    rules = [
        ("事实审核", models.RiskLevel.medium, "待编辑补充已核实来源", True),
        ("引用审核", models.RiskLevel.medium, "核心事实需绑定来源，避免无来源结论", True),
    ]
    if any(k in text for k in HIGH_RISK_KEYWORDS):
        rules.append(("敏感审核", models.RiskLevel.high, "涉及撤稿、指控、争议或具体人物，必须运营负责人终审", True))
    if any(k in text for k in RECRUIT_KEYWORDS + MEDIUM_RISK_KEYWORDS):
        rules.append(("招聘审核", models.RiskLevel.medium, "岗位、待遇、编制、截止时间必须以官方公告为准", True))
    for risk_type, level, suggestion, source_required in rules:
        finding = models.RiskFinding(
            draft_id=draft.id,
            risk_type=risk_type,
            level=level,
            excerpt=summarize(text, 80),
            suggestion=suggestion,
            source_required=source_required,
        )
        db.add(finding)
        findings.append(finding)
    draft.status = models.DraftStatus.risk_checked
    assigned_role = "operator" if any(f.level == models.RiskLevel.high for f in findings) else "reviewer"
    task = db.scalars(
        select(models.ReviewTask).where(models.ReviewTask.draft_id == draft.id).order_by(models.ReviewTask.id.desc())
    ).first()
    if not task:
        task = models.ReviewTask(draft_id=draft.id, assigned_role=assigned_role)
        db.add(task)
    else:
        task.assigned_role = assigned_role
        if task.status != models.ReviewStatus.pending:
            task.status = models.ReviewStatus.pending
            task.final_result = "重新提交待审核"
    audit(db, actor, "workspace.risk_check", "drafts", str(draft.id))
    db.commit()
    return findings


def schedule_topic(
    db: Session,
    topic_id: int,
    planned_at: datetime,
    actor: str,
    owner: str = "",
    notes: str = "",
) -> models.CalendarItem:
    topic = db.get(models.Topic, topic_id)
    if not topic:
        raise ValueError("Topic not found")
    item = db.scalars(select(models.CalendarItem).where(models.CalendarItem.topic_id == topic_id)).first()
    if not item:
        item = models.CalendarItem(topic_id=topic.id, planned_at=planned_at)
        db.add(item)
    item.planned_at = planned_at
    item.account_name = topic.target_account
    item.column_name = topic.column_name
    item.owner = owner or item.owner or "运营编辑"
    item.status = "待写作" if topic.status in {models.TopicStatus.candidate, models.TopicStatus.approved} else "生产中"
    item.risk_level = topic.risk_level
    item.notes = notes or item.notes
    topic.status = models.TopicStatus.scheduled
    audit(db, actor, "calendar.schedule", "topics", str(topic_id), {"planned_at": planned_at.isoformat()})
    db.commit()
    return item


def auto_schedule_topics(
    db: Session,
    actor: str,
    days: int = 7,
    per_day: int = 2,
    start_at: datetime | None = None,
    owner: str = "运营编辑",
) -> list[models.CalendarItem]:
    existing_topic_ids = set(db.scalars(select(models.CalendarItem.topic_id)).all())
    stmt = (
        select(models.Topic)
        .outerjoin(models.TopicScore, models.Topic.id == models.TopicScore.topic_id)
        .where(models.Topic.status == models.TopicStatus.approved)
        .where(models.Topic.risk_level != models.RiskLevel.high)
        .order_by(func.coalesce(models.TopicScore.total, 0).desc(), models.Topic.updated_at.desc())
        .limit(days * per_day * 2)
    )
    topics = [topic for topic in db.scalars(stmt).all() if topic.id not in existing_topic_ids]
    base = start_at or (datetime.utcnow() + timedelta(days=1))
    slots = []
    for offset in range(days):
        day = base + timedelta(days=offset)
        slots.append(day.replace(hour=10, minute=0, second=0, microsecond=0))
        if per_day > 1:
            slots.append(day.replace(hour=17, minute=30, second=0, microsecond=0))
        for extra in range(max(0, per_day - 2)):
            slots.append(day.replace(hour=14 + extra, minute=0, second=0, microsecond=0))
    created: list[models.CalendarItem] = []
    used_day_account: set[tuple[str, str]] = set()
    for topic in topics:
        if len(created) >= days * per_day:
            break
        slot = next(
            (
                candidate
                for candidate in slots
                if (candidate.strftime("%Y-%m-%d"), topic.target_account) not in used_day_account
            ),
            None,
        )
        if not slot:
            break
        used_day_account.add((slot.strftime("%Y-%m-%d"), topic.target_account))
        item = models.CalendarItem(
            topic_id=topic.id,
            planned_at=slot,
            account_name=topic.target_account,
            column_name=topic.column_name,
            owner=owner,
            status="待写作",
            risk_level=topic.risk_level,
            notes="自动排期：优先高分、低中风险、避免同账号同日重复。",
        )
        topic.status = models.TopicStatus.scheduled
        db.add(item)
        created.append(item)
    audit(db, actor, "calendar.auto_schedule", "calendar_items", payload={"created": len(created), "days": days})
    db.commit()
    return created


def _metric_article(db: Session, item: MetricImportItem) -> models.HistoricalArticle:
    if item.article_id:
        article = db.get(models.HistoricalArticle, item.article_id)
        if article:
            return article
    article = db.scalars(
        select(models.HistoricalArticle)
        .where(models.HistoricalArticle.account_name == item.account_name)
        .where(models.HistoricalArticle.title == item.title)
        .order_by(models.HistoricalArticle.id.desc())
    ).first()
    if article:
        if item.published_at and not article.published_at:
            article.published_at = item.published_at
        return article
    article = models.HistoricalArticle(
        account_name=item.account_name,
        title=item.title,
        body=item.title,
        published_at=item.published_at,
        summary=f"复盘数据导入文章：{item.title}",
        source_url=item.source_url,
        column_name=item.column_name or infer_column(item.account_name, item.title),
        risk_level=infer_risk(item.title),
        reusable_level="待判断",
        tags=extract_tags(item.title),
    )
    db.add(article)
    db.flush()
    db.add(models.ArticleEmbedding(article_id=article.id, vector=vectorize(article.title)))
    return article


def import_metrics(db: Session, items: list[MetricImportItem], actor: str = "system") -> int:
    count = 0
    for item in items:
        article = _metric_article(db, item)
        db.add(
            models.ArticleMetric(
                article_id=article.id,
                reads=item.reads,
                likes=item.likes,
                wows=item.wows,
                favorites=item.favorites,
                shares=item.shares,
                comments=item.comments,
                new_followers=item.new_followers,
                unfollows=item.unfollows,
            )
        )
        count += 1
    audit(db, actor, "metrics.import", "article_metrics", payload={"count": count})
    db.commit()
    return count


def sync_wechat_metrics(
    db: Session,
    account_name: str,
    start_date: date,
    end_date: date,
    actor: str = "system",
) -> dict[str, Any]:
    accounts = ["募格学术", "募格科聘"] if account_name == "全部" else [account_name]
    warnings: list[str] = []
    imported = 0
    synced_accounts: list[str] = []
    for account in accounts:
        try:
            rows = sync_article_datacube(account, start_date, end_date)
        except WeChatApiError as exc:
            warnings.append(f"{account}：{exc}")
            continue
        items = [
            MetricImportItem(
                account_name=row["account_name"],
                title=row["title"],
                published_at=row["published_at"],
                source_url=row["source_url"],
                column_name=row["column_name"] or infer_column(row["account_name"], row["title"]),
                reads=row["reads"],
                likes=row["likes"],
                wows=row["wows"],
                favorites=row["favorites"],
                shares=row["shares"],
                comments=row["comments"],
                new_followers=row["new_followers"],
                unfollows=row["unfollows"],
            )
            for row in rows
            if row.get("title")
        ]
        if items:
            imported += import_metrics(db, items, actor)
            synced_accounts.append(account)
        else:
            warnings.append(f"{account}：接口返回为空，可能该日期无群发或账号无统计权限")
    audit(
        db,
        actor,
        "metrics.wechat_sync",
        "article_metrics",
        payload={"accounts": synced_accounts, "imported": imported, "warnings": warnings},
    )
    db.commit()
    return {"imported": imported, "accounts": synced_accounts, "warnings": warnings}


def _rate(numerator: int | float, denominator: int | float) -> float:
    if not denominator:
        return 0.0
    return round(float(numerator) / float(denominator), 4)


def _title_pattern(title: str) -> str:
    if "如何" in title or "怎么" in title:
        return "方法指南"
    if "为什么" in title or "背后" in title:
        return "深度解释"
    if any(mark in title for mark in ["？", "?"]):
        return "问题式标题"
    if any(word in title for word in ["清单", "建议", "避坑", "问清"]):
        return "清单避坑"
    if any(word in title for word in ["招聘", "岗位", "博士后", "求职"]):
        return "求职招聘"
    if any(word in title for word in ["基金", "论文", "撤稿", "科研"]):
        return "学术热点"
    return "常规标题"


def build_operation_report(db: Session, period: str, account: str = "全部") -> models.OperationReport:
    metric_rows = db.scalars(select(models.ArticleMetric).order_by(models.ArticleMetric.id.desc())).all()
    rows: list[tuple[models.ArticleMetric, models.HistoricalArticle]] = []
    for metric in metric_rows:
        article = db.get(models.HistoricalArticle, metric.article_id)
        if not article:
            continue
        date_basis = article.published_at or metric.created_at
        if period and date_basis.strftime("%Y-%m") != period:
            continue
        if account != "全部" and article.account_name != account:
            continue
        rows.append((metric, article))

    totals = {
        "article_count": len(rows),
        "reads": sum(metric.reads for metric, _ in rows),
        "likes": sum(metric.likes for metric, _ in rows),
        "wows": sum(metric.wows for metric, _ in rows),
        "favorites": sum(metric.favorites for metric, _ in rows),
        "shares": sum(metric.shares for metric, _ in rows),
        "comments": sum(metric.comments for metric, _ in rows),
        "new_followers": sum(metric.new_followers for metric, _ in rows),
        "unfollows": sum(metric.unfollows for metric, _ in rows),
    }
    interactions = totals["likes"] + totals["wows"] + totals["favorites"] + totals["shares"] + totals["comments"]
    totals["interaction_rate"] = _rate(interactions, totals["reads"])
    totals["share_rate"] = _rate(totals["shares"], totals["reads"])
    totals["net_followers"] = totals["new_followers"] - totals["unfollows"]
    totals["follow_conversion_rate"] = _rate(totals["net_followers"], totals["reads"])

    by_account: dict[str, dict[str, Any]] = defaultdict(lambda: {"articles": 0, "reads": 0, "interactions": 0, "shares": 0, "net_followers": 0})
    by_column: dict[str, dict[str, Any]] = defaultdict(lambda: {"articles": 0, "reads": 0, "interactions": 0, "shares": 0})
    by_pattern: dict[str, dict[str, Any]] = defaultdict(lambda: {"articles": 0, "reads": 0, "interactions": 0})
    top_articles = []
    for metric, article in rows:
        row_interactions = metric.likes + metric.wows + metric.favorites + metric.shares + metric.comments
        account_bucket = by_account[article.account_name]
        account_bucket["articles"] += 1
        account_bucket["reads"] += metric.reads
        account_bucket["interactions"] += row_interactions
        account_bucket["shares"] += metric.shares
        account_bucket["net_followers"] += metric.new_followers - metric.unfollows
        column = article.column_name or infer_column(article.account_name, article.title)
        column_bucket = by_column[column]
        column_bucket["articles"] += 1
        column_bucket["reads"] += metric.reads
        column_bucket["interactions"] += row_interactions
        column_bucket["shares"] += metric.shares
        pattern = _title_pattern(article.title)
        pattern_bucket = by_pattern[pattern]
        pattern_bucket["articles"] += 1
        pattern_bucket["reads"] += metric.reads
        pattern_bucket["interactions"] += row_interactions
        top_articles.append(
            {
                "title": article.title,
                "account_name": article.account_name,
                "column_name": column,
                "reads": metric.reads,
                "interaction_rate": _rate(row_interactions, metric.reads),
                "share_rate": _rate(metric.shares, metric.reads),
                "net_followers": metric.new_followers - metric.unfollows,
            }
        )

    for bucket in list(by_account.values()) + list(by_column.values()) + list(by_pattern.values()):
        bucket["avg_reads"] = round(bucket["reads"] / bucket["articles"], 1) if bucket["articles"] else 0
        bucket["interaction_rate"] = _rate(bucket["interactions"], bucket["reads"])
    top_articles.sort(key=lambda item: (item["reads"], item["interaction_rate"], item["share_rate"]), reverse=True)
    account_rows = [{"name": key, **value} for key, value in sorted(by_account.items(), key=lambda item: item[1]["reads"], reverse=True)]
    column_rows = [{"name": key, **value} for key, value in sorted(by_column.items(), key=lambda item: item[1]["reads"], reverse=True)]
    pattern_rows = [{"name": key, **value} for key, value in sorted(by_pattern.items(), key=lambda item: item[1]["reads"], reverse=True)]

    top_topics = [item["title"] for item in top_articles[:5]]
    if not top_topics:
        top_topics = [topic.title for topic in db.scalars(select(models.Topic).order_by(models.Topic.updated_at.desc()).limit(5))]
    insights = []
    if totals["article_count"]:
        insights.append(f"本期纳入 {totals['article_count']} 篇文章，阅读 {totals['reads']}，互动率 {round(totals['interaction_rate'] * 100, 2)}%。")
        best_column = column_rows[0]["name"] if column_rows else "暂无栏目"
        best_pattern = pattern_rows[0]["name"] if pattern_rows else "暂无标题结构"
        insights.append(f"表现最强栏目是“{best_column}”，建议优先做系列化、翻新和双账号联动。")
        insights.append(f"标题结构上“{best_pattern}”当前表现更好，下一轮标题候选可提高该类占比。")
        if totals["share_rate"] < 0.01:
            insights.append("分享率偏低，建议增加清单、模板、核查步骤和可转发给同事的实用段落。")
        if totals["follow_conversion_rate"] <= 0:
            insights.append("净关注转化偏弱，需要减少泛资讯稿，强化账号独家判断和读者下一步行动。")
    else:
        insights.extend([
            "当前周期暂无可分析数据，请先导入阅读、点赞、在看、收藏、转发、评论和关注变化。",
            "建议至少导入最近 10 篇文章，复盘才更稳定。",
        ])
    report = models.OperationReport(
        period=period,
        account_name=account,
        summary=f"{period} 运营复盘已生成：重点看账号表现、栏目效率、标题结构、分享率和关注转化。",
        insights=insights,
        next_topics=top_topics or ["从最新监控热点中筛选科研诚信与高校人才议题", "基于真实新闻来源复盘下一轮内容方向"],
        metrics_snapshot={
            "totals": totals,
            "by_account": account_rows,
            "by_column": column_rows[:8],
            "by_title_pattern": pattern_rows,
            "top_articles": top_articles[:10],
        },
    )
    db.add(report)
    db.commit()
    return report
