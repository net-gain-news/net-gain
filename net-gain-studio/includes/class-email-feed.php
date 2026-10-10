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
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_Email_Feed {

	const FEED = 'ng-email';

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
		$title     = self::k12( html_entity_decode( get_the_title( $post ), ENT_QUOTES, 'UTF-8' ) );
		$url       = get_permalink( $post );

		return array(
			'title'          => $title,
			'url'            => $url,
			'listen_url'     => add_query_arg( 'autoplay', '1', $url ),
			'transcript_url' => $url . '#transcript',
			'image_url'      => $image_url,
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

		while ( have_posts() ) {
			the_post();
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

	/** The full card for the daily email. Pure: takes episode_data()'s array, returns HTML. */
	public static function daily_card( array $e ) {
		$img = $e['image_url']
			? '<tr><td style="padding:0 0 20px;"><a href="' . self::esc( $e['url'] ) . '"><img src="' . self::esc( $e['image_url'] ) . '" width="536" alt="' . self::esc( $e['image_alt'] )
				. '" style="display:block;width:100%;max-width:536px;height:auto;border:1px solid ' . self::BORDER . ';" /></a></td></tr>'
			: '';

		return '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">'
			. '<tr><td style="padding:0 0 16px;font-family:' . self::MONO . ';font-size:10px;line-height:12px;letter-spacing:0.12em;text-transform:uppercase;color:' . self::MUTED . ';">'
			. '<span style="display:inline-block;background:' . self::RED . ';color:#ffffff;font-weight:700;padding:5px 9px;margin-right:10px;">Latest episode</span>' . self::esc( $e['date_label'] ) . '</td></tr>'
			. $img
			. '<tr><td style="padding:0 0 14px;font-family:' . self::HEAD . ';font-size:30px;line-height:34px;font-weight:700;letter-spacing:-0.02em;color:' . self::INK . ';">'
			. '<a href="' . self::esc( $e['url'] ) . '" style="color:' . self::INK . ';text-decoration:none;">' . self::esc( $e['title'] ) . '</a></td></tr>'
			. '<tr><td style="padding:0 0 24px;font-family:' . self::BODY . ';font-size:17px;line-height:27px;color:' . self::INK . ';">' . self::esc( $e['summary'] ) . '</td></tr>'
			. '<tr><td style="padding:0 0 22px;">' . self::button( $e['listen_url'], '&#9658;&nbsp; Listen', true ) . '&nbsp;&nbsp;' . self::button( $e['transcript_url'], 'Read transcript', false ) . '</td></tr>'
			. '<tr><td style="padding:0;font-family:' . self::BODY . ';font-size:14px;line-height:22px;color:' . self::MUTED . ';">'
			. 'The show notes and every story link are on the episode page: <a href="' . self::esc( $e['url'] ) . '" style="color:' . self::ACCENT . ';text-decoration:underline;">read them on the website &rarr;</a></td></tr>'
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
			. '<a href="' . self::esc( $e['transcript_url'] ) . '" style="color:' . self::ACCENT . ';text-decoration:none;">Transcript</a></div>'
			. '</td></tr></table></td></tr></table>';
	}
}
