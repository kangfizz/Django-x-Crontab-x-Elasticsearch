#目的: 撰寫一個每個禮拜定時寄信的系統
#從es取資料 (這周對話數(ok),這周對話時間,總對話數(ok),總對話時間(ok))
#利用crontab定時執行 0 0 * * MON /var/www/html/MI_COM_django/django_venv/bin/python3 /var/www/html/MI_COM_django/MIwebsite/week_email_report.py >> /home/leo77705/vimbackup.log 2>&1
# (可從 /home/leo77705/vimbackup.log 察看結果 & error.log)
#注意,遠端主機的基本timezone可能跟您預設的django時區不同
#無論email地址是否偽造都可以傳出去
import os
os.environ.update({"DJANGO_SETTINGS_MODULE": "MIwebsite.settings"})
from elasticsearch.helpers import bulk
from elasticsearch import Elasticsearch
from datetime import datetime,timedelta
from offwebsite.models import CustomUser
#寄送email
from django.core.mail import EmailMessage,EmailMultiAlternatives

es= Elasticsearch()
# 判斷是否為星期1,如果是的話就將上禮拜的取下來
now = datetime.now()
dateline = (now - timedelta(days=7)).strftime("%Y-%m-%d")+" 至 "+now.strftime("%Y-%m-%d")
#先找尋熱門對話前3(一周)    
s1=es.search(index="manager_platform_talk", body={
    "from" : 0, "size" : 0,
    "query": {
     "constant_score" : {
      "filter":{
          "bool":{
              "must":[
                         {"range" : {
                            "lastest_time" : {
                                "gte" : "now-7d/d",
                                "lt" :  "now/d"
                            }
                         }}                        
                     ]
                }
            }   
     }
    },
    "aggs" : {
        "mes_count" : {
            "terms" : { "field" : "talk_word.keyword" }
        }
    }    
})    
mes_word_list1=s1['aggregations']['mes_count']['buckets'][:10]
mes_list = []
mes_html = ""
mcount = 1
for it in mes_word_list1:
    if it['key'] not in ['阿呆','start_learn_mode','是的']:
        mes_list.append(it)
        mes_html += str(mcount)+ ". "+ it['key'] + ": "+ str(it['doc_count']) + "次<br>"
        mcount += 1
    if mcount == 4:
        break
    
        
#所有使用者
s3=es.search(index="manager_platform", body={
    "from" : 0, "size" : 10000, #可以修超過10000筆
})
# len(s3['hits']['hits'])
userlist = s3['hits']['hits']
userdictlist = []
for sdict in s3['hits']['hits']:
    #所有使用者(單一) sdict['_source']['account']
    #當前使用者總對話數 sdict['_source']['total_message']
    #總對話時間(秒) sdict['_source']['total_talk_time']
    total_t_num = sdict['_source']['total_message']
    total_time = sdict['_source']['total_talk_time']
    m, s = divmod(total_time, 60)
    if m < 60:
        total_t = "%02d分%02d秒" % ( m, s)
    else:
        h, m = divmod(m, 60)
        total_t =  "%d小時%02d分%02d秒" % (h, m, s) 
    s2=es.search(index="manager_platform_talk", body={
        "from" : 0, "size" : 10000, #可以修超過10000筆
        "sort" : [
        { "lastest_time" : {"order" : "desc"}}, #依時間順序排下來(desc依最新)
        ],
        "query": {
         "constant_score" : {
          "filter":{
              "bool":{
                  "must":[
                            {"match_phrase": {
                                "account": sdict['_source']['account']
                            }},
                             {"range" : {
                                "lastest_time" : {
                                    "gte" : "now-7d/d",
                                    "lt" :  "now/d"
                                }
                             }}                        
                         ]
                    }
                }   
         }
        }
    })
    #這周對話數
    week_t_num = s2['hits']['total']
    #這周對話時間*
    week_total_time = 0
    for ss in range(week_t_num):
        try:
            nda = datetime.strptime(s2['hits']['hits'][ss]['_source']['lastest_time'], '%Y-%m-%d %H:%M:%S')
            nda2 = datetime.strptime(s2['hits']['hits'][ss+1]['_source']['lastest_time'], '%Y-%m-%d %H:%M:%S')
            if int((nda - nda2).total_seconds()) < 600: #彌補方案:因為先前未存入每段話的時間,這次將取間隔600秒(10分)內的間距總和
                week_total_time += int((nda - nda2).total_seconds())
        except:
            pass
    userdictlist.append({'user':sdict['_source']['account'],'period':dateline,'week_t_num':week_t_num,'week_total_time':week_total_time,'total_t_num':total_t_num,'total_time':total_time})
    
    m, s = divmod(week_total_time, 60)
    if m < 60:
        week_t = "%02d分%02d秒" % ( m, s)
    else:
        h, m = divmod(m, 60)
        week_t =  "%d小時%02d分%02d秒" % (h, m, s)        
    html_content='<div style=" width: 650px; "> \
            <div style="border: solid 1px #a6e4e7; display: block; padding: 20px; color: #fc3a52; font-size: 30px; 	font-family: \
            微軟正黑體; border-radius: 20px;">\
            <img style="margin-left: 30px;height: 80px;margin-right:500px;top: 6px;right: 6px;" src="https://www.ap-mic.com/static/MI_COM_PART/img/MI_icon_black.png" alt=""></img>\
            【亞太機器智能】每周智能對話報告<br><div style="border: none;font-size: 15px;">(期間:'+dateline+')</div>\
            </div> \
            <div style="border: solid 1px #a6e4e7; line-height: 50px; display: block; padding: 20px; font-family: \
            微軟正黑體; border-radius: 20px;"> \
            親愛的 '+CustomUser.objects.get( email= sdict['_source']['account'] ).nick_name+' 您好， \
            <br>  \
            <b>以下是上周的報告:</b><br>\
            1. 上周對話數: '+str(week_t_num)+'句<br>\
            2. 上周對話時間: '+week_t+'<br>\
            3. 目前總對話數: '+str(total_t_num)+'句<br>\
            4. 目前總對話時間: '+total_t+'<br>\
            <br>\
            <b>上週對話排行榜(前三名):</b><br>\
            '+mes_html+'\
            <br> \
            以上如有任何問題，歡迎寫信到 dsjerry2017@gmail.com\
            <br>\
            <h6>(如果您沒有申請帳號的話,請無視這封信件。)</h6> \
            <h5>Copyright © 2018 亞太機器智能(AP-MIC).</h5>\
            </div></div>'
    if  sdict['_source']['account'] == "123@gmail.com":
        towho = "leo77705@gmail.com"
    else:
        towho = sdict['_source']['account']

    msg=EmailMultiAlternatives('【亞太機器智能AP-MIC】每周智能對話報告('+dateline+')',"信箱驗證",'亞太機器智能', to=[towho])
    msg.attach_alternative(html_content, "text/html")
    msg.send()