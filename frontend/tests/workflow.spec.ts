import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
const password=process.env.TEST_ADMIN_PASSWORD || readFileSync('../backend/.env','utf8').split(/\r?\n/).find(x=>x.startsWith('ADMIN_PASSWORD='))?.slice(15);
test('login, scan, review, approve, simulate, history, settings, responsive layout',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('/');
 await page.getByLabel('Username',{exact:true}).fill('admin');
 await page.getByLabel('Password',{exact:true}).fill(password!);
 await page.getByRole('button',{name:'Sign in',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Infrastructure overview'})).toBeVisible();
 await page.getByRole('button',{name:'Run scan',exact:true}).click();
 await expect(page.getByText('Scan completed',{exact:true})).toBeVisible({timeout:30000});
 await expect(page.getByRole('link',{name:'Review idle EC2 instance',exact:true})).toBeVisible();
 await page.screenshot({path:'../../outputs/project-overview.png',fullPage:true});
 await page.getByRole('link',{name:'Review idle EC2 instance',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Why this matters'})).toBeVisible();
 const approve=page.getByRole('button',{name:'Approve recommendation'});
 if(await approve.isVisible()){
   await approve.click();
   await expect(page.getByRole('button',{name:'Simulate execution',exact:true})).toBeVisible();
 }
 const execute=page.getByRole('button',{name:'Simulate execution',exact:true});
 if(await execute.isVisible()){
   await execute.click();
   await page.getByRole('button',{name:'Confirm execution'}).click();
 }
 await expect(page.getByText('Simulated EC2 stop succeeded. No AWS action occurred.')).toBeVisible({timeout:15000});
 await page.getByRole('link',{name:'Execution history',exact:true}).click();
 await expect(page.getByText('succeeded',{exact:true})).toBeVisible();
 await page.getByRole('link',{name:'Resources',exact:true}).click();
 await expect(page.getByRole('link',{name:'demo-rds',exact:true})).toBeVisible();
 await page.getByRole('link',{name:'demo-rds',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Utilization evidence'})).toBeVisible();
 await page.getByRole('link',{name:'Settings',exact:true}).click();
 await page.getByRole('button',{name:'Validate connection'}).click();
 await expect(page.getByText('Demo connection uses generated data. No AWS request was sent.')).toBeVisible();
 await page.getByRole('button',{name:'Save preferences'}).click();
 await expect(page.getByText('Preferences saved')).toBeVisible();
 await page.setViewportSize({width:390,height:844});
 await page.getByRole('link',{name:'Overview',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Infrastructure overview'})).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
 await page.screenshot({path:'../../outputs/project-mobile.png',fullPage:true});
 expect(errors).toEqual([]);
});
