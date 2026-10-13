<?php
/**
 * Email feed for Kit's RSS-to-email automations (2026-10-10): /series/edtech/feed/ng-email/
 *
 * Kit builds the daily email and the weekly digest from an RSS feed. Its post tags (title, url, date, summary,
 * content) have no image tag, so everything the emails need that is not plain text - the episode thumbnail, the
 * Listen and Transcript buttons - has to arrive inside the feed's HTML. This feed does that, separately from the
 * show's podcast feed (which stays exactly as it is):
 *
 *   <content:encoded>  the full card for the DAILY email   ({{ post.content }} in Kit)
 *   <description>      the compact card for the WEEKLY digest ({{ post.summary }} in Kit)
 *
 * Both are email-safe (tables, inline styles, 600 px layout), in the Net Gain Edtech Denim palette, use the episode's
 * JPEG 16:9 art (email clients cannot show the WebP website art), link Listen to the episode page with ?autoplay=1 and
 * Transcript to its #transcript anchor (the same links the website's own buttons use), and deliberately carry NO story
 * links - readers go to the website episode page for those.
 *
 * Daily card (2026-10-13): one full-width "Listen now" button carrying the episode length, a single secondary text link
 * ("Transcript & source story links"), and the length stamped on the thumbnail (a cached copy of the art with a small
 * pill drawn into the bottom strip - email clients cannot overlay text on an image reliably, so it is part of the picture).
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_Email_Feed {

	const FEED      = 'ng-email';
	const MAX_ITEMS = 5;     // a week of weekday episodes: the weekly digest shows the last five, the daily email uses the newest

	// Denim palette (see design/palettes/denim and the live theme).
	const INK    = '#22293a';
	const MUTED  = '#5f6470';
	const ACCENT = '#2f5379';
	const BORDER = '#d6cab7';
	const RED    = '#d0202c';
	const HEAD   = "'Archivo','Helvetica Neue',Helvetica,Arial,sans-serif";
	const MONO   = "'IBM Plex Mono','Courier New',Courier,monospace";
	const BODY   = "'IBM Plex Sans','Helvetica Neue',Helvetica,Arial,sans-serif";

	public static function register() {
		add_action( 'init', array( __CLASS__, 'add_feed' ) );
	}

	public static function add_feed() {
		add_feed( self::FEED, array( __CLASS__, 'render_feed' ) );
	}

	/** K-12 always uses the non-breaking hyphen (U+2011) so it can never split across two lines; older episodes predate the rule. */
	public static function k12( $text ) {
		return preg_replace( '/\bK-12\b/u', "K\u{2011}12", (string) $text );
	}

	/** One episode's card inputs, read from WordPress. */
	public static function episode_data( $post ) {
		$source_id = (int) get_post_meta( $post->ID, '_ng_source_episode_id', true );
		$image_id  = $source_id ? (int) get_post_meta( $source_id, 'ng_image_16x9_id', true ) : 0;
		$image_url = $image_id ? wp_get_attachment_url( $image_id ) : '';
		$seconds   = $source_id ? (int) get_post_meta( $source_id, 'ng_audio_seconds', true ) : 0;
		$length    = self::duration_label( $seconds );
		$title     = self::k12( html_entity_decode( get_the_title( $post ), ENT_QUOTES, 'UTF-8' ) );
		$url       = get_permalink( $post );

		return array(
			'title'          => $title,
			'url'            => $url,
			'listen_url'     => add_query_arg( 'autoplay', '1', $url ),
			'transcript_url' => $url . '#transcript',
			'image_url'      => $image_url,
			'length'         => $length,
			'daily_image_url' => ( $image_id && '' !== $length ) ? self::thumb_with_length( $image_id, $length ) : $image_url,
			'image_alt'      => 'Net Gain Edtech episode: ' . $title,
			'date_label'     => get_the_date( 'M j, Y', $post ),
			'summary'        => self::k12( trim( wp_strip_all_tags( get_the_excerpt( $post ) ) ) ),
		);
	}

	public static function render_feed() {
		header( 'Content-Type: application/rss+xml; charset=' . get_option( 'blog_charset' ), true );
		header( 'X-Robots-Tag: noindex, follow' );

		$cdata = function ( $html ) {
			return '<![CDATA[' . str_replace( ']]>', ']]]]><![CDATA[>', $html ) . ']]>';
		};
		$title = 'Net Gain Edtech';
		$term  = get_queried_object();
		if ( $term && isset( $term->name ) ) {
			$title = $term->name;
		}

		echo '<?xml version="1.0" encoding="' . esc_attr( get_option( 'blog_charset' ) ) . '"?>' . "\n";
		echo '<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/" xmlns:dc="http://purl.org/dc/elements/1.1/">' . "\n<channel>\n";
		echo '<title>' . esc_html( $title ) . "</title>\n";
		echo '<link>' . esc_url( $term && isset( $term->term_id ) ? get_term_link( $term ) : home_url( '/' ) ) . "</link>\n";
		echo '<description>' . esc_html( get_bloginfo( 'description' ) ) . "</description>\n";
		echo '<language>en-US</language>' . "\n";

		$count = 0;
		while ( have_posts() && $count < self::MAX_ITEMS ) {
			the_post();
			++$count;
			$post = get_post();
			$e    = self::episode_data( $post );
			echo "<item>\n";
			echo '<title>' . esc_html( $e['title'] ) . "</title>\n";
			echo '<link>' . esc_url( $e['url'] ) . "</link>\n";
			echo '<guid isPermaLink="true">' . esc_url( $e['url'] ) . "</guid>\n";
			echo '<pubDate>' . esc_html( get_post_time( 'r', true, $post ) ) . "</pubDate>\n";
			echo '<dc:creator>' . $cdata( get_the_author_meta( 'display_name', $post->post_author ) ) . "</dc:creator>\n";
			echo '<description>' . $cdata( self::compact_card( $e ) ) . "</description>\n";
			echo '<content:encoded>' . $cdata( self::daily_card( $e ) ) . "</content:encoded>\n";
			echo "</item>\n";
		}

		echo "</channel>\n</rss>\n";
	}

	private static function esc( $text ) {
		return htmlspecialchars( (string) $text, ENT_QUOTES, 'UTF-8' );
	}

	private static function button( $url, $label, $filled ) {
		$style = $filled
			? 'background:' . self::ACCENT . ';border:1px solid ' . self::ACCENT . ';color:#ffffff;'
			: 'background:transparent;border:1px solid ' . self::ACCENT . ';color:' . self::ACCENT . ';';
		return '<a href="' . self::esc( $url ) . '" style="display:inline-block;' . $style
			. 'font-family:' . self::MONO . ';font-size:12px;line-height:16px;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;text-decoration:none;padding:12px 20px;">'
			. $label . '</a>';
	}

	/** Pure: 293 seconds -> "4:53"; an hour or more -> "1:02:03"; unknown or zero -> "". */
	public static function duration_label( $seconds ) {
		$seconds = (int) $seconds;
		if ( $seconds <= 0 ) {
			return '';
		}
		$h = intdiv( $seconds, 3600 );
		$m = intdiv( $seconds % 3600, 60 );
		$s = $seconds % 60;
		return $h > 0 ? sprintf( '%d:%02d:%02d', $h, $m, $s ) : sprintf( '%d:%02d', $m, $s );
	}

	/**
	 * A copy of the episode's 16:9 art with the length in a small cream pill at the right of its bottom strip (aligned
	 * with the show wordmark on the left). Written once to uploads/ng-email/ and reused; falls back to the plain art URL
	 * if GD, the font or the file is unavailable, so a problem here can never break the email.
	 */
	public static function thumb_with_length( $image_id, $label ) {
		$plain = (string) wp_get_attachment_url( $image_id );
		$path  = (string) get_attached_file( $image_id );
		$font  = dirname( __DIR__ ) . '/assets/email/IBMPlexMono-Medium.ttf';
		if ( '' === $label || ! is_file( $path ) || ! is_file( $font ) || ! function_exists( 'imagettftext' ) || ! function_exists( 'imagecreatefromjpeg' ) ) {
			return $plain;
		}

		$upload = wp_upload_dir();
		$dir    = $upload['basedir'] . '/ng-email';
		$key    = substr( md5( filemtime( $path ) . '|' . $label . '|v1' ), 0, 10 );
		$name   = 'thumb-' . (int) $image_id . '-' . preg_replace( '/[^0-9]/', '', $label ) . '-' . $key . '.jpg';
		$file   = $dir . '/' . $name;
		$url    = $upload['baseurl'] . '/ng-email/' . $name;
		if ( is_file( $file ) ) {
			return $url;
		}
		if ( ! wp_mkdir_p( $dir ) ) {
			return $plain;
		}

		$img = @imagecreatefromjpeg( $path );
		if ( ! $img ) {
			return $plain;
		}
		$w     = imagesx( $img );
		$h     = imagesy( $img );
		$scale = $w / 1280;

		$size = 34 * $scale * 0.75;                      // GD sizes text in points (96 dpi)
		$box  = imagettfbbox( $size, 0, $font, $label );
		$tw   = abs( $box[2] - $box[0] );
		$th   = abs( $box[7] - $box[1] );
		$padx = 20 * $scale;
		$pady = 13 * $scale;
		$pw   = (int) round( $tw + 2 * $padx );
		$ph   = (int) round( $th + 2 * $pady );
		$x    = (int) round( $w - 44 * $scale - $pw );  // right margin = the wordmark's left margin
		$y    = (int) round( $h * 0.906 - $ph / 2 );    // centred on the bottom strip, level with the wordmark

		// Draw the pill at 4x on a copy of the strip behind it, then shrink it back for smooth corners.
		$k   = 4;
		$big = imagecreatetruecolor( $pw * $k, $ph * $k );
		imagecopyresampled( $big, $img, 0, 0, $x, $y, $pw * $k, $ph * $k, $pw, $ph );
		$cream = imagecolorallocate( $big, 239, 231, 218 );
		$navy  = imagecolorallocate( $big, 31, 42, 58 );
		$r     = (int) round( 7 * $scale * $k );
		$W     = $pw * $k - 1;
		$H     = $ph * $k - 1;
		imagefilledrectangle( $big, $r, 0, $W - $r, $H, $cream );
		imagefilledrectangle( $big, 0, $r, $W, $H - $r, $cream );
		foreach ( array( array( $r, $r ), array( $W - $r, $r ), array( $r, $H - $r ), array( $W - $r, $H - $r ) ) as $c ) {
			imagefilledellipse( $big, $c[0], $c[1], $r * 2, $r * 2, $cream );
		}
		imagettftext( $big, $size * $k, 0, (int) round( $padx * $k - $box[0] * $k ), (int) round( $pady * $k + $th * $k ), $navy, $font, $label );
		imagecopyresampled( $img, $big, $x, $y, 0, 0, $pw, $ph, $pw * $k, $ph * $k );
		imagedestroy( $big );

		$ok = imagejpeg( $img, $file, 90 );
		imagedestroy( $img );
		return $ok ? $url : $plain;
	}

	/** A full-width button (a one-cell table so it is a single big tap target in every client). */
	private static function wide_button( $url, $label ) {
		return '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>'
			. '<td align="center" bgcolor="' . self::ACCENT . '" style="background:' . self::ACCENT . ';">'
			. '<a href="' . self::esc( $url ) . '" style="display:block;font-family:' . self::MONO . ';font-size:15px;line-height:20px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:#ffffff;text-decoration:none;padding:18px 20px;">'
			. $label . '</a></td></tr></table>';
	}

	/** The full card for the daily email. Pure: takes episode_data()'s array, returns HTML. */
	public static function daily_card( array $e ) {
		$length = isset( $e['length'] ) ? (string) $e['length'] : '';
		$art    = ! empty( $e['daily_image_url'] ) ? $e['daily_image_url'] : $e['image_url'];
		$img    = $art
			? '<tr><td style="padding:0 0 20px;"><a href="' . self::esc( $e['url'] ) . '"><img src="' . self::esc( $art ) . '" width="536" alt="' . self::esc( $e['image_alt'] )
				. '" style="display:block;width:100%;max-width:536px;height:auto;border:1px solid ' . self::BORDER . ';" /></a></td></tr>'
			: '';
		$label = '&#9658;&nbsp; Listen now' . ( '' !== $length ? '&nbsp;&middot;&nbsp;' . self::esc( $length ) : '' );

		return '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">'
			. '<tr><td style="padding:0 0 16px;font-family:' . self::MONO . ';font-size:10px;line-height:12px;letter-spacing:0.12em;text-transform:uppercase;color:' . self::MUTED . ';">'
			. '<span style="display:inline-block;background:' . self::RED . ';color:#ffffff;font-weight:700;padding:5px 9px;margin-right:10px;">Latest episode</span>' . self::esc( $e['date_label'] ) . '</td></tr>'
			. $img
			. '<tr><td style="padding:0 0 14px;font-family:' . self::HEAD . ';font-size:30px;line-height:34px;font-weight:700;letter-spacing:-0.02em;color:' . self::INK . ';">'
			. '<a href="' . self::esc( $e['url'] ) . '" style="color:' . self::INK . ';text-decoration:none;">' . self::esc( $e['title'] ) . '</a></td></tr>'
			. '<tr><td style="padding:0 0 24px;font-family:' . self::BODY . ';font-size:17px;line-height:27px;color:' . self::INK . ';">' . self::esc( $e['summary'] ) . '</td></tr>'
			. '<tr><td style="padding:0 0 18px;">' . self::wide_button( $e['listen_url'], $label ) . '</td></tr>'
			. '<tr><td align="center" style="padding:0;font-family:' . self::BODY . ';font-size:15px;line-height:22px;text-align:center;">'
			. '<a href="' . self::esc( $e['url'] ) . '" style="color:' . self::ACCENT . ';text-decoration:underline;">Transcript &amp; source story links &rarr;</a></td></tr>'
			. '</table>';
	}

	/** The compact card for one episode in the weekly digest. */
	public static function compact_card( array $e ) {
		$summary = $e['summary'];
		if ( function_exists( 'mb_strlen' ) && mb_strlen( $summary ) > 170 ) {
			$summary = rtrim( mb_substr( $summary, 0, 167 ), " ,;:.-" ) . '&hellip;';
		} else {
			$summary = self::esc( $summary );
		}

		$thumb = $e['image_url']
			? '<td class="ng-thumb" width="176" valign="top" style="width:176px;padding:0 20px 0 0;"><a href="' . self::esc( $e['url'] ) . '"><img src="' . self::esc( $e['image_url'] ) . '" width="176" alt="' . self::esc( $e['image_alt'] )
				. '" style="display:block;width:176px;height:auto;border:1px solid ' . self::BORDER . ';" /></a></td>'
			: '';

		return '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="border-top:1px solid ' . self::BORDER . ';"><tr><td style="padding:22px 0;">'
			. '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>' . $thumb
			. '<td class="ng-copy" valign="top" style="vertical-align:top;">'
			. '<div style="font-family:' . self::MONO . ';font-size:10px;line-height:12px;letter-spacing:0.12em;text-transform:uppercase;color:' . self::MUTED . ';padding:0 0 8px;">' . self::esc( $e['date_label'] ) . '</div>'
			. '<div style="font-family:' . self::HEAD . ';font-size:20px;line-height:24px;font-weight:700;letter-spacing:-0.015em;color:' . self::INK . ';padding:0 0 8px;"><a href="' . self::esc( $e['url'] ) . '" style="color:' . self::INK . ';text-decoration:none;">' . self::esc( $e['title'] ) . '</a></div>'
			. '<div style="font-family:' . self::BODY . ';font-size:14px;line-height:22px;color:' . self::MUTED . ';padding:0 0 12px;">' . $summary . '</div>'
			. '<div style="font-family:' . self::MONO . ';font-size:11px;line-height:14px;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;">'
			. '<a href="' . self::esc( $e['listen_url'] ) . '" style="color:' . self::ACCENT . ';text-decoration:none;">&#9658; Listen</a>'
			. '<span style="color:' . self::BORDER . ';">&nbsp;&nbsp;|&nbsp;&nbsp;</span>'
			. '<a href="' . self::esc( $e['transcript_url'] ) . '" style="color:' . self::ACCENT . ';text-decoration:none;">Transcript</a>'
			. '<span style="color:' . self::BORDER . ';">&nbsp;&nbsp;|&nbsp;&nbsp;</span>'
			. '<a href="' . self::esc( $e['url'] ) . '" style="color:' . self::ACCENT . ';text-decoration:none;">Story links</a></div>'
			. '</td></tr></table></td></tr></table>';
	}
}
