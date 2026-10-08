/** 定时和页面按钮最终共用后端日期锁；此锁仅避免同一页面挂起重复调用。 */
export function createDailyTrigger(run:()=>Promise<unknown>){
  let pending=false;
  return async()=>{
    if(pending)return;
    pending=true;
    try{await run();}catch{/* 忙碌或断线时等下次检查；已经开始的批次由持久化状态禁止重发。 */}
    finally{pending=false;}
  };
}
