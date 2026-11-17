import assert from 'node:assert/strict'
import test from 'node:test'
import { installIsolatedExecutionAdmission, currentExecutionPermit } from '../src/isolated-execution-admission.mjs'

test('native dispatch uses admission, releases errors and keeps credentials out of arguments', async () => {
  const oldUrl = process.env.MOVO_EXECUTION_ADMISSION_URL
  const oldToken = process.env.MOVO_EXECUTION_ADMISSION_TOKEN
  process.env.MOVO_EXECUTION_ADMISSION_URL='http://test/admission'
  process.env.MOVO_EXECUTION_ADMISSION_TOKEN='scoped'
  let wrapper
  const operations=[]
  try {
    const dispose = installIsolatedExecutionAdmission({on(event,fn){assert.equal(event,'tools/execute');wrapper=fn;return ()=>{}}}, {
      bridgeTools:['run_script'],request:async(url,options)=>{
        operations.push({operation:url.split('/').at(-1),body:JSON.parse(options.body)})
        return {ok:true,json:async()=>({token:`token-${operations.length}`})}
      },
    })
    const exec={name:'plugin-tool',callId:'a',agent:{id:'s'},arguments:{},signal:new AbortController().signal}
    const original=exec.signal
    await assert.rejects(wrapper(exec,async()=>{
      assert.equal(currentExecutionPermit(),'token-1')
      assert.deepEqual(exec.arguments,{})
      return wrapper({...exec,callId:'child'},async()=>{throw new Error('failed')})
    }),/failed/)
    assert.equal(operations[1].body.parent,'token-1')
    assert.deepEqual(operations.map(x=>x.operation),['acquire','acquire','release','release'])
    assert.equal(exec.signal,original)
    for (const name of ['run_script','ask_user_question','skill','present']) {
      assert.equal(await wrapper({...exec,name},async()=>42),42)
    }
    assert.equal(operations.length,4)
    dispose()
  } finally {
    if(oldUrl===undefined)delete process.env.MOVO_EXECUTION_ADMISSION_URL;else process.env.MOVO_EXECUTION_ADMISSION_URL=oldUrl
    if(oldToken===undefined)delete process.env.MOVO_EXECUTION_ADMISSION_TOKEN;else process.env.MOVO_EXECUTION_ADMISSION_TOKEN=oldToken
  }
})

test('desktop and non-isolated runtimes retain native execution without manager calls',()=>{
 const old=process.env.MOVO_EXECUTION_ADMISSION_URL
 delete process.env.MOVO_EXECUTION_ADMISSION_URL
 try {installIsolatedExecutionAdmission({on(){assert.fail('must not install')}})()}
 finally {if(old!==undefined)process.env.MOVO_EXECUTION_ADMISSION_URL=old}
})
