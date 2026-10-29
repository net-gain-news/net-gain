<?php
/**
 * The invitation landing page (netgain.news/edtech/listen/): a campaign page whose one job is the email signup.
 *
 * It is an ordinary WordPress page that uses the "Net Gain landing page" template this class adds. The page's text lives
 * in one post meta value (ng_listen_copy) edited in a "Landing page text" box on the page's own edit screen, so wording
 * changes never need a developer. The latest episode, its picture, length and the recent headlines are pulled live.
 *
 * Kept out of search engines three ways: a robots meta tag, an X-Robots-Tag header, and a Disallow line in robots.txt.
 * (Disallow alone would stop a crawler ever seeing the noindex, which is why the first two exist as well.)
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_Listen_Page {

	const TEMPLATE   = 'ng-listen';
	const META_KEY   = 'ng_listen_copy';
	const PATHS_OPT  = 'ng_listen_paths';
	const NONCE      = 'ng_listen_copy_nonce';
	const KIT_FORM   = '9946333';   // the daily list, the same form as the episode pages' signup card
	const KIT_UID    = '1f24ce821e';

	/**
	 * Every editable text, grouped for the edit screen.
	 *   type  text | rich (rich allows links, bold, italic and line breaks)
	 *   blank default = an emptied box falls back to the standard wording; hide = an emptied box removes that element
	 */
	public static function sections() {
		return array(
			'hero'     => array(
				'title'  => 'Top of the page (the signup)',
				'intro'  => 'The coloured band at the top of the page, where the email signup sits. This is the first thing a visitor sees, on a phone as well as on a computer.',
				'fields' => array(
					'eyebrow'      => array( 'Small label above the headline', 'text', 'hide', 'Net Gain Edtech · A Net Gain News production', 'The small capital-letter line above the headline. Empty hides it.' ),
					'headline'     => array( 'Headline', 'text', 'default', 'Five minutes. Every business day. The K-12 news that matters.', 'The large headline. Keep it to one or two short sentences: on a phone it wraps to about four lines. Empty restores the standard wording.' ),
					'lede'         => array( 'Sentence under the headline', 'text', 'default', 'A daily audio briefing on education technology, security and policy for district leaders. Free.', 'One or two sentences saying what the show is and who it is for. Empty restores the standard wording.' ),
					'card_kicker'  => array( 'Small label at the top of the signup box', 'text', 'hide', 'Free · every business day', 'A few words above the email box, in small capitals. Empty hides it.' ),
					'placeholder'  => array( 'Grey hint text inside the email box', 'text', 'default', 'Your work email', 'Shown inside the empty email box until the visitor types. Empty restores the standard wording.' ),
					'button'       => array( 'Signup button', 'text', 'default', 'Send me the daily episode', 'The words on the big red button. An arrow is added after them automatically; do not type one. The same wording is used on the lower signup box. Empty restores the standard wording.' ),
					'fine'         => array( 'Small print under the button', 'rich', 'default', 'One email per business day. Unsubscribe any time. We never sell your address.', 'Promises about the email, shown directly under the button. Only state what is true of the Kit list. Empty restores the standard wording.' ),
					'listen_first' => array( 'Link that jumps down to the sample episode', 'text', 'hide', 'Or hear today’s episode first', 'A quiet text link under the signup box that scrolls to the "hear today’s episode" section. A down arrow is added automatically. Empty hides the link.' ),
					'ok_title'     => array( 'After signing up: heading', 'text', 'default', 'You’re on the list', 'Replaces the email box once the visitor has signed up. Empty restores the standard wording.' ),
					'ok_text'      => array( 'After signing up: message', 'text', 'default', 'Check your inbox for a confirmation email from Net Gain Edtech. Tomorrow’s briefing arrives on its own.', 'Shown under that heading. The confirmation email comes from Kit, so keep this consistent with what Kit sends. Empty restores the standard wording.' ),
				),
			),
			'listen'   => array(
				'title'  => 'Hear today’s episode first',
				'intro'  => 'A box that plays the newest episode before the visitor signs up. The headline, picture, date and length are pulled in automatically, so this box is never out of date. If the show has no published episode yet, the whole section disappears.',
				'fields' => array(
					'listen_heading' => array( 'Section heading', 'text', 'default', 'Hear today’s episode first', 'The heading above the episode box. Empty restores the standard wording.' ),
					'listen_button'  => array( 'Play button', 'text', 'default', 'Listen now', 'The words on the outlined button. A play symbol is added automatically. The button opens the episode page and starts playing. Empty restores the standard wording.' ),
					'listen_note'    => array( 'Note under the play button', 'text', 'hide', 'Opens the episode page. No app or account needed.', 'A short reassurance under the button. Empty hides it.' ),
				),
			),
			'benefits' => array(
				'title'  => 'What you get',
				'intro'  => 'Three short boxes, then a list of the three newest headlines (pulled in automatically as plain text, not links, so they do not pull a visitor away from the signup).',
				'fields' => array(
					'benefits_heading' => array( 'Section heading', 'text', 'default', 'What you get', 'Empty restores the standard wording.' ),
					'b1_title'         => array( 'Box 1: title', 'text', 'default', 'Short', 'One word or a few words. Empty restores the standard wording.' ),
					'b1_text'          => array( 'Box 1: text', 'text', 'default', 'Five minutes, built for a commute or a coffee. A written summary and source links come with every episode.', 'One or two sentences. Empty restores the standard wording.' ),
					'b2_title'         => array( 'Box 2: title', 'text', 'default', 'Relevant', 'Empty restores the standard wording.' ),
					'b2_text'          => array( 'Box 2: text', 'text', 'default', 'Security incidents, funding and policy, and what they mean for districts like yours.', 'Empty restores the standard wording.' ),
					'b3_title'         => array( 'Box 3: title', 'text', 'default', 'Sourced', 'Empty restores the standard wording.' ),
					'b3_text'          => array( 'Box 3: text', 'text', 'default', 'Every story links to its source. A market segment follows fifty publicly traded edtech companies.', 'Empty restores the standard wording.' ),
					'recent_heading'   => array( 'Heading above the recent headlines', 'text', 'hide', 'Recent headlines', 'The three newest episode titles are listed under this heading. Empty hides the whole list.' ),
				),
			),
			'who'      => array(
				'title'  => 'Who makes it',
				'intro'  => 'The anchor’s photo, name and credential line come from the anchor’s profile (Users, then the anchor’s profile page), so change those there. The paragraph and the sponsor line are edited here.',
				'fields' => array(
					'who_heading' => array( 'Section heading', 'text', 'default', 'Who makes it', 'Empty restores the standard wording.' ),
					'who_text'    => array( 'Paragraph about the anchor', 'rich', 'default', 'Net Gain Edtech is written and anchored by Dallas Kachan. Early in his career he wrote and anchored hourly national newscasts for the Canadian Press news service. He is also Edsby’s vice president of marketing.', 'Two or three sentences. The last sentence discloses the Edsby connection; keep some form of that, because the page exists because of an Edsby invitation. Links are allowed. Empty restores the standard wording.' ),
					'sponsor'     => array( 'Sponsor line', 'rich', 'hide', 'Brought to you by the <a href="https://www.edsby.com/" target="_blank" rel="sponsored noopener">Edsby</a> student success platform for K-12.', 'Shown with the Edsby logo under the paragraph. Empty hides the line and the logo.' ),
				),
			),
			'why'      => array(
				'title'  => 'Why you are seeing this',
				'intro'  => 'The transparency note for visitors who arrive from an Edsby email. Someone at Edsby who owns privacy should approve this wording before the first email goes out.',
				'fields' => array(
					'why_heading' => array( 'Heading', 'text', 'default', 'Why you’re seeing this', 'Empty restores the standard wording.' ),
					'why_text'    => array( 'Text', 'rich', 'hide', 'You’re here because you’re connected with Edsby, which sponsors Net Gain Edtech. Signing up is optional and separate from anything you receive from Edsby.', 'Empty removes the whole section, heading included. Links are allowed.' ),
				),
			),
			'bottom'   => array(
				'title'  => 'Bottom of the page',
				'intro'  => 'A second signup box at the end of the page for visitors who read all the way down. It uses the same email box, button wording and small print as the top.',
				'fields' => array(
					'bottom_heading' => array( 'Heading above the second signup box', 'text', 'default', 'Get tomorrow’s briefing in your inbox.', 'Empty restores the standard wording.' ),
					'apps_heading'   => array( 'Heading above the podcast-app links', 'text', 'hide', 'Prefer a podcast app?', 'The Apple Podcasts, Spotify, other-apps and RSS links appear under this heading. Empty hides the links.' ),
				),
			),
			'phone'    => array(
				'title'  => 'Phone signup bar',
				'intro'  => 'On a phone, once the visitor has scrolled past the signup box, a slim bar stays at the bottom of the screen and takes them back up to it. It is never shown on larger screens.',
				'fields' => array(
					'bar_text'   => array( 'Words on the bar', 'text', 'default', 'Free daily briefing', 'Keep it very short. Empty restores the standard wording.' ),
					'bar_button' => array( 'Button on the bar', 'text', 'default', 'Sign up', 'One or two words. Empty restores the standard wording.' ),
				),
			),
		);
	}

	/** Flat key => definition list. */
	public static function fields() {
		$out = array();
		foreach ( self::sections() as $section ) {
			foreach ( $section['fields'] as $key => $def ) {
				$out[ $key ] = array(
					'label'   => $def[0],
					'type'    => $def[1],
					'blank'   => $def[2],
					'default' => $def[3],
					'help'    => $def[4],
				);
			}
		}
		return $out;
	}

	/** Pure: the text each element shows, given what was saved (a key => string map; absent keys use the standard wording). */
	public static function resolve( array $saved, array $fields ) {
		$out = array();
		foreach ( $fields as $key => $def ) {
			$value = isset( $saved[ $key ] ) && is_string( $saved[ $key ] ) ? $saved[ $key ] : $def['default'];
			if ( '' === trim( $value ) && 'default' === $def['blank'] ) {
				$value = $def['default'];
			}
			$out[ $key ] = $value;
		}
		return $out;
	}

	/** Pure: what to store from a submitted form: only known keys, and only wording that differs from the standard. */
	public static function to_store( array $submitted, array $fields ) {
		$store = array();
		foreach ( $fields as $key => $def ) {
			if ( ! isset( $submitted[ $key ] ) || ! is_string( $submitted[ $key ] ) ) {
				continue;
			}
			$value = trim( $submitted[ $key ] );
			if ( $value === $def['default'] ) {
				continue;
			}
			$store[ $key ] = $value;
		}
		return $store;
	}

	/** K-12 always uses the non-breaking hyphen (U+2011) so it can never split across two lines. */
	public static function k12( $text ) {
		return preg_replace( '/\bK-12\b/u', "K\u{2011}12", (string) $text );
	}

	/** Pure: robots.txt text with a Disallow for each path added inside the "User-agent: *" group (or a new group if there is none). */
	public static function robots_with_disallow( $robots, array $paths ) {
		$robots = (string) $robots;
		$lines  = array();
		foreach ( $paths as $path ) {
			$path = '/' . trim( (string) $path, '/' ) . '/';
			if ( '//' === $path || false !== strpos( $robots, 'Disallow: ' . $path ) ) {
				continue;
			}
			$lines[] = 'Disallow: ' . $path;
		}
		if ( ! $lines ) {
			return $robots;
		}
		$block = implode( "\n", $lines );
		if ( preg_match( '/^User-agent:\s*\*\s*$/mi', $robots, $m, PREG_OFFSET_CAPTURE ) ) {
			$end = $m[0][1] + strlen( $m[0][0] );
			return substr( $robots, 0, $end ) . "\n" . $block . substr( $robots, $end );
		}
		return rtrim( $robots ) . "\n\nUser-agent: *\n" . $block . "\n";
	}

	/** Pure: the Disallow-able path (no host) of a permalink. */
	public static function path_of( $url ) {
		$path = (string) wp_parse_url( (string) $url, PHP_URL_PATH );
		return '/' . trim( $path, '/' ) . '/';
	}

	/* ----------------------------------------------------------------- WordPress wiring */

	public static function register() {
		add_filter( 'theme_page_templates', array( __CLASS__, 'add_template' ) );
		add_filter( 'template_include', array( __CLASS__, 'use_template' ), 99 );
		add_filter( 'use_block_editor_for_post', array( __CLASS__, 'classic_editor' ), 10, 2 );
		add_action( 'load-post.php', array( __CLASS__, 'hide_content_editor' ) );
		add_action( 'add_meta_boxes_page', array( __CLASS__, 'add_meta_box' ) );
		add_action( 'save_post_page', array( __CLASS__, 'save' ), 10, 2 );
		add_action( 'save_post_page', array( __CLASS__, 'refresh_paths' ), 20 );
		add_action( 'save_post_page', array( __CLASS__, 'mark_noindex_in_aioseo' ), 30 );
		add_action( 'trashed_post', array( __CLASS__, 'refresh_paths' ) );
		add_action( 'deleted_post', array( __CLASS__, 'refresh_paths' ) );
		add_action( 'wp_enqueue_scripts', array( __CLASS__, 'enqueue' ) );
		add_filter( 'body_class', array( __CLASS__, 'body_class' ) );
		add_filter( 'wp_robots', array( __CLASS__, 'robots' ), 99 );
		add_filter( 'aioseo_robots_meta', array( __CLASS__, 'aioseo_robots' ), 99 );
		add_action( 'template_redirect', array( __CLASS__, 'send_header' ), 1 );
		add_filter( 'robots_txt', array( __CLASS__, 'robots_txt' ), 99 );
	}

	public static function is_listen_page( $post_id = 0 ) {
		$post_id = $post_id ? (int) $post_id : (int) get_queried_object_id();
		return $post_id && 'page' === get_post_type( $post_id ) && self::TEMPLATE === get_post_meta( $post_id, '_wp_page_template', true );
	}

	public static function add_template( $templates ) {
		$templates[ self::TEMPLATE ] = 'Net Gain landing page (email signup)';
		return $templates;
	}

	public static function use_template( $template ) {
		if ( is_page() && self::is_listen_page() ) {
			return NET_GAIN_PLUGIN_DIR . 'templates/listen.php';
		}
		return $template;
	}

	public static function classic_editor( $use_block, $post ) {
		return ( $post && self::is_listen_page( $post->ID ) ) ? false : $use_block;
	}

	/** The page body is not used (the text comes from the box below), so the empty editor would only confuse. */
	public static function hide_content_editor() {
		$post_id = isset( $_GET['post'] ) ? (int) $_GET['post'] : 0; // phpcs:ignore WordPress.Security.NonceVerification
		if ( $post_id && self::is_listen_page( $post_id ) ) {
			remove_post_type_support( 'page', 'editor' );
		}
	}

	public static function body_class( $classes ) {
		if ( is_page() && self::is_listen_page() ) {
			$classes[] = 'ng-listen-page';
		}
		return $classes;
	}

	public static function enqueue() {
		if ( ! is_page() || ! self::is_listen_page() ) {
			return;
		}
		$base = plugin_dir_url( NET_GAIN_PLUGIN_FILE );
		$css  = NET_GAIN_PLUGIN_DIR . 'assets/listen.css';
		$js   = NET_GAIN_PLUGIN_DIR . 'assets/listen.js';
		wp_enqueue_style( 'ng-listen', $base . 'assets/listen.css', array(), NET_GAIN_VERSION . '.' . (int) @filemtime( $css ) );
		wp_enqueue_script( 'ng-listen', $base . 'assets/listen.js', array(), NET_GAIN_VERSION . '.' . (int) @filemtime( $js ), true );
	}

	/* ----------------------------------------------------------------- kept out of search engines */

	public static function robots( $robots ) {
		if ( is_page() && self::is_listen_page() ) {
			$robots = array( 'noindex' => true, 'nofollow' => true, 'noarchive' => true );
		}
		return $robots;
	}

	public static function aioseo_robots( $attributes ) {
		if ( is_page() && self::is_listen_page() ) {
			return array( 'noindex' => 'noindex', 'nofollow' => 'nofollow', 'noarchive' => 'noarchive' );
		}
		return $attributes;
	}

	public static function send_header() {
		if ( is_page() && self::is_listen_page() ) {
			header( 'X-Robots-Tag: noindex, nofollow, noarchive' );
		}
	}

	/** AIOSEO builds its sitemap from its own per-page robots setting, so the page is marked noindex there too (as the subscribe and welcome pages are). */
	public static function mark_noindex_in_aioseo( $post_id ) {
		if ( ! self::is_listen_page( $post_id ) || ! class_exists( '\\AIOSEO\\Plugin\\Common\\Models\\Post' ) ) {
			return;
		}
		try {
			\AIOSEO\Plugin\Common\Models\Post::savePost(
				(int) $post_id,
				array(
					'default'   => false,
					'noindex'   => true,
					'nofollow'  => true,
					'noarchive' => true,
				)
			);
		} catch ( \Throwable $e ) {
			return;
		}
	}

	public static function refresh_paths() {
		$ids   = get_posts(
			array(
				'post_type'      => 'page',
				'post_status'    => 'publish',
				'posts_per_page' => 20,
				'fields'         => 'ids',
				'meta_key'       => '_wp_page_template', // phpcs:ignore WordPress.DB.SlowDBQuery
				'meta_value'     => self::TEMPLATE,      // phpcs:ignore WordPress.DB.SlowDBQuery
			)
		);
		$paths = array();
		foreach ( $ids as $id ) {
			$paths[] = self::path_of( get_permalink( $id ) );
		}
		update_option( self::PATHS_OPT, array_values( array_unique( $paths ) ), false );
	}

	public static function robots_txt( $text ) {
		return self::robots_with_disallow( $text, (array) get_option( self::PATHS_OPT, array() ) );
	}

	/* ----------------------------------------------------------------- the edit screen */

	public static function allowed_html() {
		return array(
			'a'      => array( 'href' => true, 'target' => true, 'rel' => true ),
			'strong' => array(),
			'em'     => array(),
			'br'     => array(),
		);
	}

	public static function add_meta_box( $post ) {
		if ( ! self::is_listen_page( $post->ID ) ) {
			return;
		}
		add_meta_box( 'ng-listen-copy', 'Landing page text', array( __CLASS__, 'render_meta_box' ), 'page', 'normal', 'high' );
	}

	public static function render_meta_box( $post ) {
		$fields = self::fields();
		$saved  = get_post_meta( $post->ID, self::META_KEY, true );
		$values = self::resolve( is_array( $saved ) ? $saved : array(), $fields );
		wp_nonce_field( 'ng_listen_copy_' . $post->ID, self::NONCE );
		?>
		<style>
			.ng-lc-intro{max-width:760px;line-height:1.5}
			.ng-lc-sec{margin:22px 0 0;padding-top:14px;border-top:1px solid #dcdcde}
			.ng-lc-sec h3{margin:0 0 4px;font-size:15px}
			.ng-lc-sec>p{margin:0 0 12px;color:#50575e;max-width:760px}
			.ng-lc-f{margin:0 0 16px;max-width:760px}
			.ng-lc-f label{display:block;font-weight:600;margin-bottom:4px}
			.ng-lc-f input[type=text],.ng-lc-f textarea{width:100%}
			.ng-lc-h{margin:4px 0 0;color:#50575e;font-size:12.5px;line-height:1.45}
			.ng-lc-std{margin:3px 0 0;color:#787c82;font-size:12px}
		</style>
		<div class="ng-lc-intro">
			<p>Every piece of wording on this page is edited here. Change a box and press <strong>Update</strong> above or at the right. Under each box you will find what it does, what an empty box does, and the standard wording so you can always put it back.</p>
			<p>The newest episode’s picture, headline, date and length, the three recent headlines and the anchor’s photo are filled in automatically and are not edited here. Typing K-12 with an ordinary hyphen is fine; the page uses the non-breaking hyphen for you.</p>
			<p>This page asks search engines not to list it or crawl it. It is not linked from anywhere on the site; only people who are sent the address can find it.</p>
		</div>
		<?php foreach ( self::sections() as $sid => $section ) : ?>
			<div class="ng-lc-sec">
				<h3><?php echo esc_html( $section['title'] ); ?></h3>
				<p><?php echo esc_html( $section['intro'] ); ?></p>
				<?php foreach ( $section['fields'] as $key => $def ) : ?>
					<?php $id = 'ng-lc-' . $key; ?>
					<div class="ng-lc-f">
						<label for="<?php echo esc_attr( $id ); ?>"><?php echo esc_html( $def[0] ); ?></label>
						<?php if ( 'rich' === $def[1] || strlen( $def[3] ) > 80 ) : ?>
							<textarea id="<?php echo esc_attr( $id ); ?>" name="ng_listen[<?php echo esc_attr( $key ); ?>]" rows="3"><?php echo esc_textarea( $values[ $key ] ); ?></textarea>
						<?php else : ?>
							<input type="text" id="<?php echo esc_attr( $id ); ?>" name="ng_listen[<?php echo esc_attr( $key ); ?>]" value="<?php echo esc_attr( $values[ $key ] ); ?>">
						<?php endif; ?>
						<p class="ng-lc-h"><?php echo esc_html( $def[4] ); ?></p>
						<p class="ng-lc-std">Standard wording: <?php echo esc_html( wp_strip_all_tags( $def[3] ) ); ?></p>
					</div>
				<?php endforeach; ?>
			</div>
		<?php endforeach; ?>
		<?php
	}

	public static function save( $post_id, $post ) {
		if ( defined( 'DOING_AUTOSAVE' ) && DOING_AUTOSAVE ) {
			return;
		}
		if ( ! isset( $_POST[ self::NONCE ] ) || ! wp_verify_nonce( sanitize_text_field( wp_unslash( $_POST[ self::NONCE ] ) ), 'ng_listen_copy_' . $post_id ) ) {
			return;
		}
		if ( ! current_user_can( 'edit_post', $post_id ) ) {
			return;
		}
		$fields    = self::fields();
		$raw       = isset( $_POST['ng_listen'] ) && is_array( $_POST['ng_listen'] ) ? wp_unslash( $_POST['ng_listen'] ) : array(); // phpcs:ignore WordPress.Security.ValidatedSanitizedInput
		$submitted = array();
		foreach ( $fields as $key => $def ) {
			if ( ! isset( $raw[ $key ] ) || ! is_string( $raw[ $key ] ) ) {
				continue;
			}
			$submitted[ $key ] = 'rich' === $def['type'] ? wp_kses( $raw[ $key ], self::allowed_html() ) : sanitize_text_field( $raw[ $key ] );
		}
		update_post_meta( $post_id, self::META_KEY, self::to_store( $submitted, $fields ) );
	}

	/* ----------------------------------------------------------------- the page itself */

	public static function copy( $post_id ) {
		$saved = get_post_meta( $post_id, self::META_KEY, true );
		return self::resolve( is_array( $saved ) ? $saved : array(), self::fields() );
	}

	public static function text( array $copy, $key ) {
		return esc_html( self::k12( isset( $copy[ $key ] ) ? $copy[ $key ] : '' ) );
	}

	public static function rich( array $copy, $key ) {
		return wp_kses( self::k12( isset( $copy[ $key ] ) ? $copy[ $key ] : '' ), self::allowed_html() );
	}

	/** The newest published episodes of a show (the same ordering as the "latest" redirect). */
	public static function recent_episodes( $show_slug, $count ) {
		if ( '' === (string) $show_slug ) {
			return array();
		}
		return get_posts(
			array(
				'post_type'      => 'podcast',
				'post_status'    => 'publish',
				'posts_per_page' => (int) $count,
				'orderby'        => 'date',
				'order'          => 'DESC',
				'tax_query'      => array( array( 'taxonomy' => 'series', 'field' => 'slug', 'terms' => $show_slug ) ),
			)
		);
	}

	/** One signup form. $which makes the field ids unique when the form appears twice. */
	public static function form_html( array $copy, $which ) {
		$id = 'ngl-email-' . sanitize_key( $which );
		ob_start();
		?>
		<form class="ngl-form" action="https://app.kit.com/forms/<?php echo esc_attr( self::KIT_FORM ); ?>/subscriptions" method="post" data-sv-form="<?php echo esc_attr( self::KIT_FORM ); ?>" data-uid="<?php echo esc_attr( self::KIT_UID ); ?>" data-format="inline" data-version="5" data-ngl-form="<?php echo esc_attr( $which ); ?>">
			<ul data-element="errors" data-group="alert" class="ngl-errors"></ul>
			<div data-element="fields" class="ngl-fields">
				<label class="ngl-sr" for="<?php echo esc_attr( $id ); ?>">Email address</label>
				<input id="<?php echo esc_attr( $id ); ?>" class="ngl-input" type="email" name="email_address" placeholder="<?php echo esc_attr( self::k12( $copy['placeholder'] ) ); ?>" required autocomplete="email" inputmode="email">
				<button type="submit" class="ngl-btn"><span><?php echo self::text( $copy, 'button' ); ?></span> <span class="ngl-arrow" aria-hidden="true">&rarr;</span></button>
			</div>
			<div data-element="success" data-group="alert" class="ngl-ok" hidden><strong class="arch"><?php echo self::text( $copy, 'ok_title' ); ?></strong><span><?php echo self::text( $copy, 'ok_text' ); ?></span></div>
		</form>
		<p class="ngl-fine"><?php echo self::rich( $copy, 'fine' ); ?></p>
		<?php
		return ob_get_clean();
	}
}
