import assert from 'node:assert/strict'
import { createServer } from 'node:http'
import { mkdtemp, readFile, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'
import { KernelRuntime } from '../src/kernel-runtime.mjs'

test('official DSH command dispatch uses admission while retaining native execution', async () => {
  const root=await mkdtemp(join(tmpdir(),'movo-native-admission-'))
  const oldUrl=process.env.MOVO_EXECUTION_ADMISSION_URL
  const oldToken=process.env.MOVO_EXECUTION_ADMISSION_TOKEN
  let turns=0
  const admission=[]
  const server=createServer(async(req,res)=>{
    let text='';for await(const chunk of req)text+=chunk
    JSON.parse(text)
    if(req.url.startsWith('/admission/')){
      admission.push(req.url.split('/').at(-1))
      res.writeHead(200,{'content-type':'application/json'}).end(JSON.stringify({token:'opaque-test-permit'}));return
    }
    const events=turns++===0 ? [
      {type:'tool-call',id:'native-command',name:process.platform==='win32'?'pwsh':'bash',arguments:JSON.stringify({
        command:'node -e "require(\'fs\').writeFileSync(\'admitted.txt\', \'verified\')"',description:'Verify native execution',
      })}, {type:'finish',reason:{kind:'tool-calls'}},
    ]:[{type:'text-delta',text:'Completed.'},{type:'finish',reason:{kind:'stop'}}]
    res.writeHead(200,{'content-type':'application/x-ndjson'}).end(events.map(x=>JSON.stringify(x)).join('\n')+'\n')
  })
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve))
  const base=`http://127.0.0.1:${server.address().port}`
  process.env.MOVO_EXECUTION_ADMISSION_URL=base+'/admission'
  process.env.MOVO_EXECUTION_ADMISSION_TOKEN='scoped-test'
  const runtime=new KernelRuntime({runtimeId:'audit',isolationKey:'audit',profileVersion:'audit',storageRoot:root,
    modelProfile:{profileVersion:'audit',modelInstanceId:'test',modelName:'test',gatewayUrl:base+'/model',accessToken:'test'}})
  try{
    await runtime.start()
    await runtime.createSession({sessionId:'admission-e2e',presetId:'code',cwd:root})
    runtime.send({sessionId:'admission-e2e',mode:'prompt',content:[{type:'text',data:{text:'Run the command.'}}],temporalContext:{captured_at_utc:new Date().toISOString(),user_local_time:new Date().toISOString(),user_timezone:'UTC'}})
    const deadline=Date.now()+15000
    while(!runtime.events('admission-e2e',-1).some(event=>event.nativeType==='turn/end')){
      if(Date.now()>deadline)throw new Error('Native admission E2E timed out')
      await new Promise(resolve=>setTimeout(resolve,20))
    }
    assert.equal(await readFile(join(root,'admitted.txt'),'utf8'),'verified')
    assert.deepEqual(admission,['acquire','release'])
  }finally{
    await runtime.dispose()
    if(oldUrl===undefined)delete process.env.MOVO_EXECUTION_ADMISSION_URL;else process.env.MOVO_EXECUTION_ADMISSION_URL=oldUrl
    if(oldToken===undefined)delete process.env.MOVO_EXECUTION_ADMISSION_TOKEN;else process.env.MOVO_EXECUTION_ADMISSION_TOKEN=oldToken
    await new Promise(resolve=>server.close(resolve));await rm(root,{recursive:true,force:true})
  }
})
