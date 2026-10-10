<?php
/**
 * Unit checks for the pure logic in includes/class-photo-library.php (eligibility, runway advice, upload checks).
 * The plugin has no PHP test runner, so this is a plain script:
 *
 *     php net-gain-studio/tests/photo-library-test.php      (prints PASS/FAIL lines, ends with ALL PASSED)
 */

define( 'ABSPATH', '/x/' );
function register_post_type() {}
function get_post_meta() { return ''; }
require __DIR__ . '/../includes/class-photo-library.php';

$L='Net_Gain_Photo_Library'; $fail=0;
function check($name,$cond){ global $fail; echo ($cond?'PASS ':'FAIL ').$name."\n"; if(!$cond) $fail++; }

// eligibility
$p=array('status'=>'ready','last_used'=>'');
check('never used is eligible', $L::eligibility($p,90,'2026-10-09')['eligible']===true);
check('used 10 days ago is resting', $L::eligibility(array('status'=>'ready','last_used'=>'2026-09-29'),90,'2026-10-09')['eligible']===false);
$e=$L::eligibility(array('status'=>'ready','last_used'=>'2026-07-11'),90,'2026-10-09');
check('used exactly 90 days ago is eligible again', $e['eligible']===true && $e['days_since']===90);
check('available_on is last_used + cooldown', $L::eligibility(array('status'=>'ready','last_used'=>'2026-09-29'),90,'2026-10-09')['available_on']==='2026-12-28');
check('retired is never eligible', $L::eligibility(array('status'=>'retired','last_used'=>''),90,'2026-10-09')['eligible']===false);
check('pending is never eligible', $L::eligibility(array('status'=>'pending_tags','last_used'=>''),90,'2026-10-09')['eligible']===false);

// stats / runway advice
$photos=array();
for($i=0;$i<30;$i++) $photos[]=array('status'=>'ready','last_used'=>'','topics'=>array('general'),'people'=>$i<10?'none':'identifiable','flags'=>array());
$s=$L::stats($photos,90,'2026-10-09',5);
check('30 eligible at 5/week = 6 weeks, level ok', $s['eligible_now']===30 && $s['weeks_of_cover']==6.0 && $s['level']==='ok');
$s=$L::stats(array_slice($photos,0,20),90,'2026-10-09',5);
check('20 eligible = 4 weeks -> low', $s['level']==='low');
$s=$L::stats(array_slice($photos,0,10),90,'2026-10-09',5);
check('10 eligible = 2 weeks -> urgent', $s['level']==='urgent');
check('empty library is urgent with a message', $L::stats(array(),90,'2026-10-09',5)['level']==='urgent');
$few=array(); for($i=0;$i<40;$i++) $few[]=array('status'=>'ready','last_used'=>'','topics'=>array('k12'),'people'=>$i<2?'none':'identifiable','flags'=>array());
$s=$L::stats($few,90,'2026-10-09',5);
check('thin on no-faces photos is flagged', $s['eligible_no_faces']===2 && $s['level']!=='ok' && strpos(implode(' ',$s['messages']),'without identifiable people')!==false);
check('topic counts: k12 photos count for k12 only', $s['eligible_by_topic']['k12']===40 && $s['eligible_by_topic']['security']===0);
check('general topic photos count for every topic', $L::stats($photos,90,'2026-10-09',5)['eligible_by_topic']['security']===30);
$mixed=array(array('status'=>'ready','last_used'=>'2026-10-01','topics'=>array(),'people'=>'none'),array('status'=>'retired'),array('status'=>'pending_tags'));
$s=$L::stats($mixed,90,'2026-10-09',5);
check('cooling/retired/pending are counted separately', $s['cooling_down']===1 && $s['retired']===1 && $s['pending']===1 && $s['eligible_now']===0);

// uploads
check('AI metadata (IPTC) is detected', $L::scan_provenance('xx<Iptc4xmpExt:DigitalSourceType>http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia</Iptc4xmpExt:DigitalSourceType>')!==array());
check('composite AI edit is detected', count($L::scan_provenance('compositeWithTrainedAlgorithmicMedia'))>=1);
check('known generator names are detected', $L::scan_provenance('Software: Midjourney v6')!==array());
check('a normal camera file passes', $L::scan_provenance("\xff\xd8\xff\xe1 Exif Canon EOS R5 Adobe Photoshop Lightroom")===array());
check('a Spanish caption does not false-positive', $L::scan_provenance('Imagen de una escuela en Madrid')===array());
check('too small is rejected', $L::check_dimensions(600,900)!=='');
check('4000x2667 is accepted', $L::check_dimensions(4000,2667)==='');
check('low-res flag under 2200 short side', $L::is_low_res(3000,2000)===true && $L::is_low_res(4000,2667)===false);
echo $fail? "FAILURES: $fail\n" : "ALL PASSED\n";
