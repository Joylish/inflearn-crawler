import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys

from contextlib import closing
from multiprocessing import Pool, Manager
from itertools import repeat

import re
from itertools import chain
import time, csv
import json
from dbIO import readDB, insertDB

import nltk
from nltk.corpus import stopwords
from ckonlpy.tag import Twitter, Postprocessor
from ckonlpy.utils import load_wordset, load_ngram

twitter = Twitter()
stopwordsKR = load_wordset('cleansing_data/korean_stopwords.txt', encoding='ANSI')
customStopwordsEN = load_wordset('cleansing_data/english_stopwords.txt', encoding='ANSI')
stopwordsEN = customStopwordsEN.union(set(stopwords.words('english')))
ngrams = load_ngram('cleansing_data/korean_ngram.txt')
userdicts = load_wordset('cleansing_data/korean_user_dict.txt')
twitter.add_dictionary(list(userdicts), 'Noun', force=True)


def connectWebDriver(web):
    options = webdriver.ChromeOptions()
    options.add_argument("disable-gpu")
    options.add_argument("headless")
    options.add_argument("lang=ko_KR")

    # 브라우저 화면 크기에 따라 미디어 쿼리 등에 따라 element 구조가
    # 달라질 수 있으므로 고정시키고 시작하기
    options.add_argument('--start-maximized')

    options.add_argument(
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/84.0.4147.125 Safari/537.36")

    driver = webdriver.Chrome('chromedriver/chromedriver', options=options)
    driver.maximize_window()
    # 헤더 탐지 피하기
    driver.execute_script("Object.defineProperty(navigator, 'plugins', {get: function() {return[1, 2, 3, 4, 5];},});")
    driver.execute_script("Object.defineProperty(navigator, 'languages', {get: function() {return ['ko-KR', 'ko']}})")
    driver.execute_script(
        "const getParameter = WebGLRenderingContext.getParameter;WebGLRenderingContext.prototype.getParameter = function(parameter) {if (parameter === 37445) {return 'NVIDIA Corporation'} if (parameter === 37446) {return 'NVIDIA GeForce GTX 980 Ti OpenGL Engine';}return getParameter(parameter);};")

    driver.implicitly_wait(2)
    driver.get(web)
    driver.implicitly_wait(2)

    return driver


def getCoursesPages():
    categories = ['it-programming', 'it', 'data-science']
    pages = []
    for category in categories:
        res = requests.get(f'https://www.inflearn.com/courses/{category}')
        html = res.text
        soup = BeautifulSoup(html, "html.parser")
        pageElements = soup.find("ul", class_="pagination-list").find_all("li")
        for pageNumber in range(1, int(pageElements[-1].get_text()) + 1):
            pages.append([category, f'https://www.inflearn.com/courses/{category}?page={pageNumber}'])
        print(pages)
    return pages


def scrollPage(driver):
    SCROLL_PAUSE_TIME = 0.5
    last_height = driver.execute_script("return document.body.scrollHeight")
    while True:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(SCROLL_PAUSE_TIME)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight-50);")
        time.sleep(SCROLL_PAUSE_TIME)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height


def getCourses(coursesPage, courseList):
    # coursesPage[1] 예시: 'https://www.inflearn.com/courses/{category}?page={pageNumber}'
    driver = connectWebDriver(coursesPage[1])
    action = ActionChains(driver)
    # courseElements = driver.find_elements_by_xpath('//a[@class="course_card_front"]')
    courseElements = driver.find_elements_by_xpath('//div[@class="card course course_card_item"]')
    for courseElement in courseElements:
        aTag = courseElement.find_element_by_class_name("course_card_front")

        course = []
        # 강의 카테고리
        course.append(coursesPage[0])
        # url = f'{aTag.get_attribute("href")}'
        url = f'{aTag.get_attribute("href")}#reviews'
        course.append(url)
        courseList.append(course)
        print(course)
        courseUrl = {"url": url, "category": coursesPage[0]}
        insertDB("courseUrl", courseUrl)
    driver.quit()


def scrapCourses(coursesPages):
    courseList = manager.list()
    with closing(Pool(processes=5)) as pool:
        pool.starmap(getCourses, zip(coursesPages, repeat(courseList)))

    print('카테고리별 강의명 저장 완료!')
    return courseList


def tokenize(text):
    englishTokens = nltk.word_tokenize(re.sub(f'[^a-zA-Z]', ' ', text).strip())
    # english = [token for token in englishTokens if token not in stopwordsEN]
    postprocessor = Postprocessor(twitter, passtags='Noun', ngrams=ngrams, stopwords=stopwordsKR)
    koreanWords = postprocessor.pos(text)
    korean = [word[0] for word in koreanWords if len(word[0]) > 1]
    tokens = []
    tokens.extend(korean)
    tokens.extend(englishTokens)
    return tokens

def createCourseInfo(contents):
    headers = ['url', '카테고리', '강의명', '리뷰수', '수강생수', '강의요약', '강의에서 할 수 있는 것', '강의후기', '강의요약_명사', '강의에서 할 수 있는 것_명사', '강의후기_명사']
    recruitInfo = {header: value for header, value in zip(headers, contents)}
    return recruitInfo

def hasxpath(driver, xpath):
    try:
        driver.find_element_by_xpath(xpath)
        return True
    except:
        return False

def getCourse(course):
    pattern = '[^0-9a-zA-Zㄱ-힗%:.~ #+\n]'
    print(course)
    # course[1] 예시: 'https://www.inflearn.com/course/aws-starter#inquires'
    # driver = connectWebDriver(course[1])
    driver = connectWebDriver(course['url'])

    titleElement = driver.find_element_by_xpath('//*[@id="main"]/div[1]/div/div/div[1]/div/div[2]/div[1]')
    reviewCountElement = driver.find_element_by_xpath(
        '/html/body/div[1]/main/div[1]/div/div/div[1]/div/div[2]/div[2]/div[1]/span[2]')
    studentCountElement = driver.find_element_by_xpath(
        '//*[@id="main"]/div[1]/div/div/div[1]/div/div[2]/div[2]/div[1]/span[3]')
    summaryElement = driver.find_element_by_css_selector('#description > div.course_summary.description_sub')
    canDoElements = driver.find_elements_by_css_selector('#description > div.can_do.description_sub > ul > li')

    # category = course[0]
    category = course['category']
    title = titleElement.text
    summary = summaryElement.text
    # summary = re.sub(pattern=pattern, repl='', string=summaryElement.text)
    reviewCount = re.findall("\d+", reviewCountElement.text)
    studentCount = re.findall("\d+", studentCountElement.text)
    canDos = [canDoElement.text for canDoElement in canDoElements] if canDoElements else []
    summaryTokens = tokenize(summary)
    canDoTokens = []
    for canDo in canDos:
        canDoTokens.extend(tokenize(canDo))

    if hasxpath(driver, '//div[@class="review_list"]/button'):
        driver.execute_script("arguments[0].scrollIntoView();", driver.find_element_by_xpath('//*[@id="reviews"]/div[2]/button'))
        driver.find_element_by_xpath('//div[@class="review_list"]/button').send_keys(Keys.ENTER)

    reviewElements = driver.find_elements_by_css_selector('#reviews > div.review_list')
    reviews = [reviewElement.text for reviewElement in reviewElements] if reviewElements else []
    reviewTokens = []
    for review in reviews:
        reviewTokens.extend(tokenize(review))
    contents = []
    # contents.append(course[1])
    contents.append(course['url'])
    contents.append(category)
    contents.append(title)
    contents.extend(reviewCount)
    contents.extend(studentCount)
    contents.append(summary)
    contents.append(canDos)
    contents.append(reviews)
    contents.append(summaryTokens)
    contents.append(canDoTokens)
    contents.append(reviewTokens)

    courseInfo = createCourseInfo(contents)

    insertDB("course", courseInfo)
    print(courseInfo)
    driver.quit()


def scrapCourse(courses):

    with closing(Pool(processes=3)) as pool:
        pool.map(getCourse, courses)

    print('카테고리별 강의명 저장 완료!')
    return courses


if __name__ == '__main__':
    manager = Manager()

    coursePages = getCoursesPages()
    courses = scrapCourses(coursePages)
    # print(courses)
    # courses = readDB('courseUrl')
    # print(courses)
    # courses=[{'_id': '5f5508e88bb5431cb17a5c11', 'url': 'https://www.inflearn.com/course/ios#inquires', 'category': 'it-programming'}]
    scrapCourse(courses)
    # scrapCourse([['data-science',
    #               'https://www.inflearn.com/course/node-js-%EA%B5%90%EA%B3%BC%EC%84%9C#reviews']])
